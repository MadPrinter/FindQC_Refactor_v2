#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商品ID抓取程序

功能说明：
1. 从 findqc.com API 抓取指定分类范围内的商品ID列表
2. 调用 getCategoryProducts 接口，按分类ID和分页获取商品数据
3. 支持多线程并发抓取多个分类（默认8个线程）
4. 自动遍历每个分类的所有页面（直到 hasMore=False）
5. 将抓取的数据按分类ID保存到 goods_data_tree/{分类ID}/page_{页码}.json
6. 跳过没有数据的分类（hasMore=False 且 page=1）

输入：
- 配置参数：START_CAT_ID（起始分类ID）、END_CAT_ID（结束分类ID）

输出：
- goods_data_tree/{分类ID}/page_{页码}.json：每个分类每页的商品数据 JSON 文件

配置：
- BASE_URL：API 接口地址
- START_CAT_ID：起始分类ID（默认3000）
- END_CAT_ID：结束分类ID（默认10000）
- MAX_WORKERS：并发线程数（默认8）
- SIZE：每页商品数量（默认20）
"""

import requests
import json
import os
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置区域 ---
BASE_URL = "https://findqc.com/api/goods/getCategoryProducts"
SAVE_DIR = "goods_data_tree"  # 保存数据的根目录
SIZE = 20
MAX_WORKERS = 8       # 线程数 (同时抓取8个分类)
START_CAT_ID = 3000     # 从分类ID 0 开始
END_CAT_ID = 10000     # 结束分类ID (根据需要调整，或者写大一点)
# ----------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

# 确保根目录存在
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

def fetch_category(cat_id):
    """
    抓取单个分类的所有页面
    """
    page = 1
    # 临时计数，看看这个分类到底有没有货
    saved_count = 0
    
    # 为该分类创建文件夹
    cat_dir = os.path.join(SAVE_DIR, str(cat_id))
    
    # 这里的循环是遍历 Page
    while True:
        try:
            # 构造请求参数
            params = {
                "catalogueId": cat_id,
                "currencyType": "USD",
                "langType": "en",
                "page": page,
                "size": SIZE
            }

            # 发送请求
            response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=10)
            
            if response.status_code != 200:
                print(f"[!] ID:{cat_id} Page:{page} 请求失败 code:{response.status_code}")
                break # 网络错误跳出，防止死循环

            res_json = response.json()

            # --- 核心判断逻辑 ---
            # 获取 data 内部的数据
            inner_data = res_json.get("data", {})
            
            # 安全获取 hasMore，如果取不到默认为 False
            has_more = inner_data.get("hasMore", False)

            # 如果 hasMore 为 False，根据你的要求：不保存，直接跳下一个分类
            if not has_more:
                # 只有当第一页就是 hasMore=False 时，才说明这个分类可能是完全空的
                if page == 1:
                    print(f"[-] ID:{cat_id} 无数据 (hasMore=False)，跳过。")
                else:
                    print(f"[ok] ID:{cat_id} 抓取完成，共 {saved_count} 页。")
                break

            # --- 如果代码走到这里，说明 hasMore 是 True，需要保存 ---
            
            # 确保分类文件夹存在 (延迟创建，防止创建大量空文件夹)
            if not os.path.exists(cat_dir):
                os.makedirs(cat_dir)

            filename = os.path.join(cat_dir, f"page_{page}.json")
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(res_json, f, ensure_ascii=False, indent=2)

            print(f"[+] ID:{cat_id} Page:{page} 已保存")
            
            saved_count += 1
            page += 1
            
            # 稍微延时，礼貌爬虫
            time.sleep(random.uniform(0.2, 0.5))

        except Exception as e:
            print(f"[Err] ID:{cat_id} Page:{page} 出错: {e}")
            break

def main():
    print(f"开始任务，ID范围: {START_CAT_ID} - {END_CAT_ID}")
    
    # 生成要遍历的 ID 列表
    cat_ids = list(range(START_CAT_ID, END_CAT_ID + 1))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        futures = {executor.submit(fetch_category, cid): cid for cid in cat_ids}
        
        for future in as_completed(futures):
            # 这里主要是为了捕获线程里未捕获的异常，或者做进度统计
            cid = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"ID:{cid} 线程抛出异常: {exc}")

    print("所有任务执行完毕。")

if __name__ == "__main__":
    main()