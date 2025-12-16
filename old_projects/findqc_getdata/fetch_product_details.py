#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商品详情抓取程序

功能说明：
1. 从 findqc.com API 获取商品的详细信息（详情、图片、SKU等）
2. 调用 detail 接口获取商品基本信息
3. 调用 atlas 接口分页获取商品的主图、SKU图、QC图等图片信息
4. 将数据存储到 SQLite 数据库（findqc_local_data.db）
5. 支持高并发处理（默认20个线程）
6. 创建多个数据表：
   - product_details_full：商品详情扩展信息
   - product_skus：商品SKU规格信息
   - product_media：商品图片信息（主图、SKU图、QC图等）

输入：
- findqc_local_data.db：数据库文件（如果不存在会自动创建）
- 需要从 goods_data_tree 目录或其他来源获取商品ID列表

输出：
- findqc_local_data.db：包含商品详情、SKU、图片等完整信息的 SQLite 数据库

配置：
- DB_NAME：数据库文件名（默认 findqc_local_data.db）
- MAX_WORKERS：并发线程数（默认20）
- ATLAS_PAGE_SIZE：图片接口每页数量（默认10）
- URL_DETAIL：商品详情接口地址
- URL_ATLAS：商品图片接口地址
"""

import sqlite3
import requests
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置 ---
DB_NAME = "findqc_local_data.db"
MAX_WORKERS = 20  # 高并发
ATLAS_PAGE_SIZE = 10

# 接口
URL_DETAIL = "https://findqc.com/api/goods/detail"
URL_ATLAS = "https://findqc.com/api/goods/atlas"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

# 线程锁
db_lock = threading.Lock()
# Session 复用连接
session = requests.Session()
session.headers.update(HEADERS)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. 详情扩展表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_details_full (
            product_id TEXT PRIMARY KEY,
            title TEXT,
            price TEXT,
            to_price TEXT,
            freight TEXT,
            to_freight TEXT,
            item_url TEXT,
            shop_id TEXT,
            shop_name TEXT,
            shop_data_json TEXT,     -- 完整店铺JSON
            category_list_json TEXT, -- 分类层级JSON
            site_meta_json TEXT,     -- 网站Meta信息
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. SKU 表 (规格属性)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_skus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            prop_id TEXT,       -- e.g. "0"
            prop_name TEXT,     -- e.g. "color classification"
            option_id TEXT,     -- e.g. "9682939157"
            option_name TEXT,   -- e.g. "Green Cowboy"
            option_pic_url TEXT -- 对应的SKU图片
        )
    ''')

    # 3. 媒体总表 (包含 图片、视频、QC元数据)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            url TEXT,
            media_type TEXT,   -- 'image' 或 'video'
            source_type TEXT,  -- 'main'(主图), 'sku'(规格图), 'detail_qc'(详情QC), 'atlas_qc'(图集QC), 'atlas_video'(图集视频)
            
            -- QC 专属元数据
            create_time INTEGER,
            seat_name TEXT,    -- e.g. "Top view"
            sku_name TEXT,     -- e.g. "colour:10;SIZE:36"
            atlas_id TEXT,     -- 属于哪个图集ID
            
            UNIQUE(product_id, url, source_type) -- 避免完全重复
        )
    ''')

    # 4. 进度表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fetch_status (
            product_id TEXT PRIMARY KEY,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_result(pid, details, skus, media_list):
    """原子化写入数据库"""
    if not details and not skus and not media_list:
        return

    with db_lock:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            # 1. 存详情
            if details:
                cursor.execute('''
                    INSERT OR REPLACE INTO product_details_full 
                    (product_id, title, price, to_price, freight, to_freight, item_url, shop_id, shop_name, shop_data_json, category_list_json, site_meta_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', details)

            # 2. 存 SKU (先删旧的再插新的，防止重复堆积)
            if skus:
                cursor.execute("DELETE FROM product_skus WHERE product_id = ?", (pid,))
                cursor.executemany('''
                    INSERT INTO product_skus (product_id, prop_id, prop_name, option_id, option_name, option_pic_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', skus)

            # 3. 存 Media
            if media_list:
                cursor.executemany('''
                    INSERT OR IGNORE INTO product_media 
                    (product_id, url, media_type, source_type, create_time, seat_name, sku_name, atlas_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', media_list)

            # 4. 标记完成
            cursor.execute("INSERT OR REPLACE INTO fetch_status (product_id, status) VALUES (?, 'done')", (pid,))
            
            conn.commit()
        except Exception as e:
            print(f"[DB Error] {pid}: {e}")
        finally:
            conn.close()

def process_item(row):
    goods_id, item_id, mall_type = row
    
    # 临时存储数据的容器
    details_tuple = None
    skus_list = []
    media_list = [] # 格式: (pid, url, type, source, time, seat, sku, atlas_id)

    # ==========================
    # 1. 请求详情页 (Detail)
    # ==========================
    try:
        # 注意：这里 notNeedQc=false，因为我们需要详情页里的 QC 数据
        params = {"itemId": item_id, "mallType": mall_type, "currencyType": "USD", "langType": "en", "notNeedQc": "false"}
        resp = session.get(URL_DETAIL, params=params, timeout=10)
        
        if resp.status_code == 200:
            full_json = resp.json()
            data_root = full_json.get("data", {})
            inner_data = data_root.get("data", {})
            
            if inner_data:
                # A. 提取详情基本信息
                shop_info = inner_data.get("shopInfo", {})
                details_tuple = (
                    goods_id,
                    inner_data.get("title"),
                    inner_data.get("price"),
                    inner_data.get("toPrice"),
                    inner_data.get("freight"),
                    inner_data.get("toFreight"),
                    inner_data.get("itemUrl"),
                    str(shop_info.get("id", "")),
                    shop_info.get("name"),
                    json.dumps(shop_info, ensure_ascii=False),
                    json.dumps(data_root.get("categoryList"), ensure_ascii=False),
                    json.dumps(data_root.get("siteMeta"), ensure_ascii=False)
                )

                # B. 提取主图 (picList)
                for url in inner_data.get("picList", []):
                    media_list.append((goods_id, url, 'image', 'main', 0, None, None, None))

                # C. 提取 SKU (propsList)
                for prop in inner_data.get("propsList", []):
                    p_id = prop.get("id")
                    p_name = prop.get("name")
                    for opt in prop.get("optionList", []):
                        # 存入 SKU 表
                        skus_list.append((
                            goods_id, p_id, p_name, opt.get("id"), opt.get("name"), opt.get("picUrl")
                        ))
                        # 如果 SKU 有图，也存入媒体表方便统一查看
                        if opt.get("picUrl"):
                            media_list.append((goods_id, opt.get("picUrl"), 'image', 'sku', 0, None, None, None))

                # D. 提取详情页自带 QC (qcList)
                for qc in inner_data.get("qcList", []):
                    media_list.append((
                        goods_id, qc.get("url"), 'image', 'detail_qc', 
                        qc.get("time"), qc.get("seatName"), qc.get("skuName"), None
                    ))

    except Exception as e:
        print(f"[Detail Err] ID:{goods_id} - {e}")
        return

    # ==========================
    # 2. 请求图集 (Atlas)
    # ==========================
    page = 1
    while True:
        try:
            params = {"page": page, "size": ATLAS_PAGE_SIZE, "goodsId": goods_id, "itemId": item_id, "mallType": mall_type}
            resp = session.get(URL_ATLAS, params=params, timeout=10)
            if resp.status_code != 200: break
            
            atlas_json = resp.json()
            atlas_data = atlas_json.get("data", {})
            atlas_list = atlas_data.get("atlasList", [])
            
            if not atlas_list: break

            for item in atlas_list:
                a_id = item.get("atlasId")
                
                # E. 图集里的 QC 图片
                for qc in item.get("qcList", []):
                    media_list.append((
                        goods_id, qc.get("url"), 'image', 'atlas_qc', 
                        qc.get("time"), qc.get("seatName"), qc.get("skuName"), str(a_id)
                    ))
                
                # F. 图集里的 视频
                for vid in item.get("videoList", []):
                    media_list.append((
                        goods_id, vid.get("url"), 'video', 'atlas_video', 
                        vid.get("time"), None, None, str(a_id)
                    ))
            
            if atlas_data.get("hasMore") is False:
                break
            page += 1

        except Exception as e:
            print(f"[Atlas Err] ID:{goods_id} - {e}")
            break

    # ==========================
    # 3. 入库
    # ==========================
    save_result(goods_id, details_tuple, skus_list, media_list)
    # print(f"[OK] {goods_id}")

def get_tasks():
    if not os.path.exists(DB_NAME): return []
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 查所有商品
    cursor.execute("SELECT id, item_id, mall_type FROM products")
    all_products = cursor.fetchall()
    # 查已完成
    try:
        cursor.execute("SELECT product_id FROM fetch_status")
        done = {row[0] for row in cursor.fetchall()}
    except: done = set()
    conn.close()
    return [r for r in all_products if str(r[0]) not in done]

import os
if __name__ == "__main__":
    if not os.path.exists(DB_NAME):
        print("请先运行之前的导入脚本生成数据库文件！")
        exit()

    init_db()
    tasks = get_tasks()
    print(f"总任务数: {len(tasks)}")
    
    count = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_item, t): t for t in tasks}
        
        for f in as_completed(futures):
            count += 1
            if count % 50 == 0:
                print(f"进度: {count}/{len(tasks)}")
            try: f.result()
            except: pass

    print("全部完成。")