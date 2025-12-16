#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商品数据导入程序

功能说明：
1. 从 goods_data_tree 目录读取 JSON 文件（由 fetch_product_ids.py 生成）
2. 解析 JSON 文件中的商品数据
3. 将商品数据导入到 SQLite 数据库（findqc_local_data.db）
4. 创建 products 表存储商品基本信息（ID、标题、价格、图片URL、分类ID、QC图数量等）
5. 支持批量导入，自动遍历所有分类目录和分页文件
6. 记录数据来源文件，方便排查问题

输入：
- goods_data_tree/：包含商品数据的目录结构
  - {分类ID}/page_{页码}.json：每个分类每页的商品数据

输出：
- findqc_local_data.db：包含商品基本信息的 SQLite 数据库

配置：
- DATA_DIR：商品数据目录（默认 goods_data_tree）
- DB_NAME：数据库文件名（默认 findqc_local_data.db）
"""

import os
import json
import sqlite3
import time

# --- 配置区域 ---
# 你之前保存 JSON 文件的根目录文件夹名称
DATA_DIR = "goods_data_tree" 
# 生成的数据库文件名
DB_NAME = "findqc_local_data.db"
# ----------------

def init_db(conn):
    """初始化数据库表结构"""
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            mall_type TEXT,
            item_id TEXT,
            title TEXT,
            pic_url TEXT,
            price TEXT,
            to_price TEXT,
            status TEXT,
            category_id INTEGER,
            qc_pic_cnt INTEGER,
            qc_video_cnt INTEGER,
            
            -- 店铺信息
            shop_id TEXT,
            shop_name TEXT,
            shop_type TEXT,
            
            -- 记录来源文件 (方便排查)
            source_file TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

def parse_json_file(filepath):
    """读取并解析单个 JSON 文件，返回提取出的数据列表"""
    items_to_save = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = json.load(f)
            
        # 根据你提供的结构，商品列表在 data -> data
        # 使用 .get 防止某些字段不存在报错
        outer_data = content.get('data')
        
        # 某些情况文件可能是空的或者结构不对
        if not outer_data or not isinstance(outer_data, dict):
            return []

        product_list = outer_data.get('data')
        
        if not product_list or not isinstance(product_list, list):
            return []

        # 提取字段
        for item in product_list:
            shop_info = item.get('shopInfo') or {}
            
            # 构建存入数据库的元组
            row = (
                str(item.get('id')),
                item.get('mallType'),
                str(item.get('itemId')),
                item.get('title'),
                item.get('picUrl'),
                item.get('price'),
                item.get('toPrice'),
                item.get('status'),
                item.get('categoryId'),
                item.get('qcPicCnt', 0),
                item.get('qcVideoCnt', 0),
                
                # 店铺信息
                str(shop_info.get('id', '')),
                shop_info.get('name', ''),
                shop_info.get('type', ''),
                
                # 来源文件名 (只保留文件名，不要全路径)
                os.path.basename(filepath)
            )
            items_to_save.append(row)
            
    except Exception as e:
        print(f"[错误] 解析文件 {filepath} 失败: {e}")
        return []

    return items_to_save

def main():
    if not os.path.exists(DATA_DIR):
        print(f"错误: 找不到文件夹 '{DATA_DIR}'，请修改脚本中的 DATA_DIR 变量。")
        return

    print(f"开始从 '{DATA_DIR}' 导入数据到 '{DB_NAME}' ...")
    start_time = time.time()

    conn = sqlite3.connect(DB_NAME)
    init_db(conn)
    cursor = conn.cursor()

    total_files = 0
    total_records = 0
    batch_buffer = []
    BATCH_SIZE = 5000  # 攒够 5000 条再一次性写入，极大提高速度

    # 遍历目录
    for root, dirs, files in os.walk(DATA_DIR):
        for file in files:
            if file.endswith(".json"):
                filepath = os.path.join(root, file)
                
                # 解析数据
                rows = parse_json_file(filepath)
                
                if rows:
                    batch_buffer.extend(rows)
                    total_records += len(rows)
                
                total_files += 1
                
                # 打印进度 (每处理 100 个文件显示一次)
                if total_files % 100 == 0:
                    print(f"已处理 {total_files} 个文件, 当前缓存 {len(batch_buffer)} 条数据...")

                # 批量写入数据库
                if len(batch_buffer) >= BATCH_SIZE:
                    cursor.executemany('''
                        INSERT OR REPLACE INTO products (
                            id, mall_type, item_id, title, pic_url, price, to_price, 
                            status, category_id, qc_pic_cnt, qc_video_cnt,
                            shop_id, shop_name, shop_type, source_file
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', batch_buffer)
                    conn.commit()
                    batch_buffer = [] # 清空缓存

    # 处理剩余的数据
    if batch_buffer:
        cursor.executemany('''
            INSERT OR REPLACE INTO products (
                id, mall_type, item_id, title, pic_url, price, to_price, 
                status, category_id, qc_pic_cnt, qc_video_cnt,
                shop_id, shop_name, shop_type, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', batch_buffer)
        conn.commit()

    conn.close()
    
    end_time = time.time()
    print(f"\n======== 导入完成 ========")
    print(f"总耗时: {end_time - start_time:.2f} 秒")
    print(f"处理文件数: {total_files}")
    print(f"入库数据条数: {total_records}")

if __name__ == "__main__":
    main()