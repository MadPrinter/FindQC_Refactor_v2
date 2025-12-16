#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据提取和清洗脚本

功能说明：
1. 从 SQLite 数据库（findqc_local_data.db）中提取商品数据
2. 关联查询多个表（products, product_details_full, product_media, product_skus）
3. 提取商品的主图、SKU图、QC图等图片 URL
4. 根据配置限制每种图片类型的数量（主图、SKU图、QC图各最多3张）
5. 支持根据销售数据文件筛选商品（只保留在销售文件中的商品）
6. 输出清洗后的 JSON 格式数据到 cleaned_data.json

输入：
- SQLite 数据库文件（findqc_local_data.db）
- 可选的销售数据筛选文件（sales.json）

输出：
- cleaned_data.json：包含商品ID、价格、URL、图片列表等信息的 JSON 文件

配置：
- 所有配置参数在 config.py 中
- 包括图片数量限制、数据库表名、输出字段映射等
"""

import sqlite3
import json
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
from collections import defaultdict

import config


def normalize_field_name(name: str) -> str:
    """
    归一化字段名，用于模糊匹配
    将字段名转换为小写，移除下划线和特殊字符
    """
    return re.sub(r'[_\s-]', '', name.lower())


def find_matching_field(target: str, fields: List[str]) -> Optional[str]:
    """
    在字段列表中查找匹配的目标字段（模糊匹配）
    """
    target_normalized = normalize_field_name(target)
    
    for field in fields:
        if normalize_field_name(field) == target_normalized:
            return field
    
    # 如果精确匹配失败，尝试部分匹配
    for field in fields:
        if target_normalized in normalize_field_name(field) or normalize_field_name(field) in target_normalized:
            return field
    
    return None


def get_table_schema(conn: sqlite3.Connection, table_name: str) -> List[Dict[str, str]]:
    """
    获取表的结构信息
    """
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    
    schema = []
    for col in columns:
        schema.append({
            'cid': col[0],
            'name': col[1],
            'type': col[2],
            'notnull': col[3],
            'default_value': col[4],
            'pk': col[5]
        })
    
    return schema


def list_all_tables(conn: sqlite3.Connection) -> List[str]:
    """
    获取数据库中所有表名
    """
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    return tables


def analyze_database_structure(conn: sqlite3.Connection):
    """
    分析数据库结构，打印所有表的信息
    """
    tables = list_all_tables(conn)
    
    print(f"\n发现 {len(tables)} 个表: {tables}\n")
    
    for table in tables:
        if table.startswith('sqlite_'):
            continue
        schema = get_table_schema(conn, table)
        field_names = [col['name'] for col in schema]
        
        print(f"表 '{table}' 的字段:")
        for col in schema:
            print(f"  - {col['name']} ({col['type']})")
        print()


def fetch_main_images(conn: sqlite3.Connection, product_id: str, max_count: int = None) -> List[str]:
    """
    从 product_media 表获取主页图片（source_type = 'main'）
    """
    if max_count is None:
        max_count = config.MAX_MAIN_IMAGES
    
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT url FROM {config.PRODUCT_MEDIA_TABLE} WHERE product_id = ? AND source_type = ? AND media_type = ? ORDER BY id LIMIT ?",
        (product_id, config.MAIN_IMAGE_SOURCE_TYPE, config.MAIN_IMAGE_MEDIA_TYPE, max_count)
    )
    rows = cursor.fetchall()
    return [row[0] for row in rows if row[0]]


def fetch_sku_images(conn: sqlite3.Connection, product_id: str, max_count: int = None) -> List[str]:
    """
    从 product_media 表获取 SKU 图片（source_type = 'sku'）
    如果 product_media 中没有，则从 product_skus 表获取
    """
    if max_count is None:
        max_count = config.MAX_SKU_IMAGES
    
    cursor = conn.cursor()
    
    # 首先尝试从 product_media 获取
    cursor.execute(
        f"SELECT DISTINCT url FROM {config.PRODUCT_MEDIA_TABLE} WHERE product_id = ? AND source_type = ? AND media_type = ? ORDER BY id LIMIT ?",
        (product_id, config.SKU_IMAGE_SOURCE_TYPE, config.SKU_IMAGE_MEDIA_TYPE, max_count)
    )
    rows = cursor.fetchall()
    urls = [row[0] for row in rows if row[0]]
    
    # 如果数量不足，从 product_skus 表补充
    if len(urls) < max_count:
        cursor.execute(
            f"SELECT DISTINCT option_pic_url FROM {config.PRODUCT_SKUS_TABLE} WHERE product_id = ? AND option_pic_url IS NOT NULL AND option_pic_url != '' LIMIT ?",
            (product_id, max_count - len(urls))
        )
        sku_rows = cursor.fetchall()
        for row in sku_rows:
            if row[0] and row[0] not in urls:
                urls.append(row[0])
    
    return urls[:max_count]


def fetch_qc_images(conn: sqlite3.Connection, product_id: str, max_count: int = None) -> List[str]:
    """
    从 product_media 表获取 QC 图片（source_type = 'atlas_qc' 或 'detail_qc'）
    """
    if max_count is None:
        max_count = config.MAX_QC_IMAGES
    
    cursor = conn.cursor()
    # 构建 IN 子句的占位符
    placeholders = ','.join(['?'] * len(config.QC_IMAGE_SOURCE_TYPES))
    cursor.execute(
        f"SELECT url FROM {config.PRODUCT_MEDIA_TABLE} WHERE product_id = ? AND source_type IN ({placeholders}) AND media_type = ? ORDER BY id LIMIT ?",
        (product_id, *config.QC_IMAGE_SOURCE_TYPES, config.QC_IMAGE_MEDIA_TYPE, max_count)
    )
    rows = cursor.fetchall()
    return [row[0] for row in rows if row[0]]


def load_sales_filter_item_ids(sales_file_path: Path) -> set:
    """
    加载销售筛选文件，提取所有的 itemId 集合
    
    Args:
        sales_file_path: 销售数据文件路径（可以是 Path 对象或字符串）
        
    Returns:
        itemId 集合，如果文件不存在或格式错误则返回空集合
    """
    # 处理路径：如果是字符串，转换为 Path；如果是 Path，确保是绝对路径
    if isinstance(sales_file_path, str):
        # 如果是相对路径，尝试在当前目录和脚本目录查找
        base_path = Path(__file__).parent
        possible_paths = [
            Path(sales_file_path),
            base_path / sales_file_path,
            base_path / f"{sales_file_path}.json"
        ]
    else:
        base_path = Path(__file__).parent
        possible_paths = [
            sales_file_path,
            base_path / sales_file_path,
            base_path / f"{sales_file_path}.json" if not str(sales_file_path).endswith('.json') else base_path / sales_file_path
        ]
    
    # 尝试找到存在的文件
    actual_path = None
    for path in possible_paths:
        if path.exists():
            actual_path = path
            break
    
    if not actual_path:
        return set()
    
    try:
        with open(actual_path, 'r', encoding='utf-8') as f:
            sales_data = json.load(f)
        
        # 支持两种格式：
        # 1. 数组格式: [{"itemId": "123", "sales30": 10}, ...]
        # 2. 对象格式: {"itemId1": {...}, "itemId2": {...}}
        item_ids = set()
        
        if isinstance(sales_data, list):
            # 数组格式
            for item in sales_data:
                if isinstance(item, dict):
                    item_id = item.get('itemId')
                    if item_id:
                        item_ids.add(str(item_id))
        elif isinstance(sales_data, dict):
            # 对象格式，key 就是 itemId
            item_ids = set(str(k) for k in sales_data.keys())
        
        return item_ids
        
    except Exception as e:
        print(f"警告: 加载销售筛选文件失败: {e}")
        return set()


def clean_record(
    base_record: Dict[str, Any],
    details_record: Optional[Dict[str, Any]],
    conn: sqlite3.Connection,
    product_id: str
) -> Dict[str, Any]:
    """
    清洗单条记录，关联多个表的数据
    """
    cleaned = {
        'id': base_record.get('id', ''),
        'mallType': base_record.get('mall_type', ''),
        'itemId': base_record.get('item_id', ''),
        'toPrice': base_record.get('to_price', ''),
        'itemUrl': details_record.get('item_url', '') if details_record else '',
        'mainImages': fetch_main_images(conn, product_id),
        'skuImages': fetch_sku_images(conn, product_id),
        'qcImages': fetch_qc_images(conn, product_id),
    }
    
    return cleaned


def main():
    """
    主函数
    """
    db_path = config.DB_PATH
    
    if not db_path.exists():
        print(f"错误: 数据库文件 {db_path} 不存在")
        return
    
    print("=" * 60)
    print("开始分析数据库结构...")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row  # 使用 Row 工厂，方便按列名访问
        
        # 1. 分析数据库结构
        analyze_database_structure(conn)
        
        # 2. 检查必要的表是否存在
        cursor = conn.cursor()
        placeholders = ','.join(['?'] * len(config.REQUIRED_TABLES))
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name IN ({placeholders})", config.REQUIRED_TABLES)
        required_tables = [row[0] for row in cursor.fetchall()]
        
        if config.PRODUCTS_TABLE not in required_tables:
            print(f"错误: 找不到 '{config.PRODUCTS_TABLE}' 表")
            conn.close()
            return
        
        print("=" * 60)
        print("开始提取数据...")
        print("=" * 60)
        
        # 2.5. 加载销售筛选数据（如果启用）
        sales_filter_item_ids = set()
        sales_filter_enabled = False
        if config.ENABLE_SALES_FILTER and config.SALES_FILTER_FILE:
            print(f"加载销售筛选文件: {config.SALES_FILTER_FILE}")
            sales_filter_item_ids = load_sales_filter_item_ids(config.SALES_FILTER_FILE)
            if sales_filter_item_ids:
                print(f"  ✓ 成功加载 {len(sales_filter_item_ids)} 个 itemId 用于筛选")
                sales_filter_enabled = True
            else:
                print(f"  ⚠ 警告: 销售筛选文件为空或不存在，将不进行筛选")
                if config.ENABLE_SALES_FILTER:
                    print(f"  提示: 如果不需要筛选，请在 config.py 中设置 ENABLE_SALES_FILTER = False")
        
        # 3. 查询基础商品数据
        # 使用 LEFT JOIN 关联 product_details_full 表获取 item_url
        query = f"""
        SELECT 
            p.id,
            p.mall_type,
            p.item_id,
            p.to_price,
            d.item_url
        FROM {config.PRODUCTS_TABLE} p
        LEFT JOIN {config.PRODUCT_DETAILS_TABLE} d ON p.id = d.product_id
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        print(f"找到 {len(rows)} 条记录")
        
        # 4. 清洗数据
        print("开始清洗数据...")
        cleaned_data = []
        
        # 为了优化性能，批量获取图片数据
        # 先获取所有 product_id
        all_product_ids = [row['id'] for row in rows]
        
        # 批量预加载图片数据（可选优化，如果数据量太大可以去掉）
        print("  预加载图片数据...")
        main_images_cache = defaultdict(list)
        sku_images_cache = defaultdict(list)
        qc_images_cache = defaultdict(list)
        
        # 批量查询主页图片
        placeholders = ','.join(['?'] * len(all_product_ids))
        cursor.execute(
            f"""
            SELECT product_id, url 
            FROM {config.PRODUCT_MEDIA_TABLE} 
            WHERE product_id IN ({placeholders}) 
            AND source_type = ? 
            AND media_type = ?
            ORDER BY product_id, id
            """,
            (*all_product_ids, config.MAIN_IMAGE_SOURCE_TYPE, config.MAIN_IMAGE_MEDIA_TYPE)
        )
        for row in cursor.fetchall():
            if len(main_images_cache[row['product_id']]) < config.MAX_MAIN_IMAGES:
                main_images_cache[row['product_id']].append(row['url'])
        
        # 批量查询 SKU 图片
        cursor.execute(
            f"""
            SELECT DISTINCT product_id, url 
            FROM {config.PRODUCT_MEDIA_TABLE} 
            WHERE product_id IN ({placeholders}) 
            AND source_type = ? 
            AND media_type = ?
            ORDER BY product_id, id
            """,
            (*all_product_ids, config.SKU_IMAGE_SOURCE_TYPE, config.SKU_IMAGE_MEDIA_TYPE)
        )
        for row in cursor.fetchall():
            if len(sku_images_cache[row['product_id']]) < config.MAX_SKU_IMAGES:
                sku_images_cache[row['product_id']].append(row['url'])
        
        # 批量查询 QC 图片
        qc_placeholders = ','.join(['?'] * len(config.QC_IMAGE_SOURCE_TYPES))
        cursor.execute(
            f"""
            SELECT product_id, url 
            FROM {config.PRODUCT_MEDIA_TABLE} 
            WHERE product_id IN ({placeholders}) 
            AND source_type IN ({qc_placeholders}) 
            AND media_type = ?
            ORDER BY product_id, id
            """,
            (*all_product_ids, *config.QC_IMAGE_SOURCE_TYPES, config.QC_IMAGE_MEDIA_TYPE)
        )
        for row in cursor.fetchall():
            if len(qc_images_cache[row['product_id']]) < config.MAX_QC_IMAGES:
                qc_images_cache[row['product_id']].append(row['url'])
        
        # 如果 SKU 图片不足，从 product_skus 表补充
        cursor.execute(
            f"""
            SELECT DISTINCT product_id, option_pic_url 
            FROM {config.PRODUCT_SKUS_TABLE} 
            WHERE product_id IN ({placeholders}) 
            AND option_pic_url IS NOT NULL 
            AND option_pic_url != ''
            ORDER BY product_id, id
            """,
            all_product_ids
        )
        for row in cursor.fetchall():
            pid = row['product_id']
            url = row['option_pic_url']
            if len(sku_images_cache[pid]) < config.MAX_SKU_IMAGES and url not in sku_images_cache[pid]:
                sku_images_cache[pid].append(url)
        
        print(f"  预加载完成: 主页图片 {len(main_images_cache)} 个商品, SKU图片 {len(sku_images_cache)} 个商品, QC图片 {len(qc_images_cache)} 个商品")
        
        # 5. 组装清洗后的数据
        filtered_count = 0
        total_before_filter = len(rows)
        matched_item_ids = set()  # 记录匹配到的 itemId
        
        for idx, row in enumerate(rows):
            if (idx + 1) % config.PROGRESS_INTERVAL == 0:
                print(f"  处理进度: {idx + 1}/{len(rows)}")
            
            product_id = row['id']
            item_id = str(row['item_id'] or '').strip()  # 去除前后空格
            
            # 如果启用了销售筛选，检查 itemId 是否在筛选列表中
            if sales_filter_enabled and sales_filter_item_ids:
                if item_id not in sales_filter_item_ids:
                    filtered_count += 1
                    continue  # 跳过不在筛选列表中的商品
                else:
                    matched_item_ids.add(item_id)
            
            details_record = {'item_url': row['item_url']} if row['item_url'] else None
            
            cleaned_record = {
                'id': product_id,
                'mallType': row['mall_type'] or '',
                'itemId': item_id,
                'toPrice': row['to_price'] or '',
                'itemUrl': row['item_url'] or '',
                'mainImages': main_images_cache.get(product_id, [])[:config.MAX_MAIN_IMAGES],
                'skuImages': sku_images_cache.get(product_id, [])[:config.MAX_SKU_IMAGES],
                'qcImages': qc_images_cache.get(product_id, [])[:config.MAX_QC_IMAGES],
            }
            
            cleaned_data.append(cleaned_record)
        
        # 显示筛选统计信息
        print(f"完成清洗，共 {len(cleaned_data)} 条记录")
        print()
        if sales_filter_enabled:
            # 计算未匹配的 itemId
            unmatched_item_ids = sales_filter_item_ids - matched_item_ids
            print("=" * 60)
            print("销售筛选统计:")
            print(f"  筛选前商品数: {total_before_filter:,}")
            print(f"  筛选后商品数: {len(cleaned_data):,}")
            print(f"  过滤掉商品数: {filtered_count:,}")
            print(f"  筛选保留率: {len(cleaned_data)/total_before_filter*100:.2f}%")
            print()
            print(f"  筛选文件包含的 itemId 数: {len(sales_filter_item_ids):,}")
            print(f"  数据库中匹配到的 itemId 数: {len(matched_item_ids):,}")
            print(f"  数据库中未找到的 itemId 数: {len(unmatched_item_ids):,}")
            if len(unmatched_item_ids) > 0 and len(unmatched_item_ids) <= 20:
                print(f"  未找到的 itemId 示例（前20个）: {list(unmatched_item_ids)[:20]}")
            elif len(unmatched_item_ids) > 20:
                print(f"  未找到的 itemId 示例（前20个）: {list(unmatched_item_ids)[:20]}")
                print(f"  ... 还有 {len(unmatched_item_ids) - 20} 个未显示")
            print("=" * 60)
            print()
        elif config.ENABLE_SALES_FILTER:
            print("  ⚠ 注意: 销售筛选已启用但筛选文件未加载，所有商品均被保留")
            print()
        
        # 6. 导出 JSON
        print("=" * 60)
        print(f"导出数据到 {config.OUTPUT_FILE}...")
        print("=" * 60)
        
        output_path = config.OUTPUT_FILE
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
        
        print(f"成功导出 {len(cleaned_data)} 条记录到 {output_path}")
        print(f"文件大小: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        # 打印一些统计信息
        print("\n统计信息:")
        main_count = sum(1 for r in cleaned_data if r['mainImages'])
        sku_count = sum(1 for r in cleaned_data if r['skuImages'])
        qc_count = sum(1 for r in cleaned_data if r['qcImages'])
        url_count = sum(1 for r in cleaned_data if r['itemUrl'])
        print(f"  有主页图片的商品: {main_count}")
        print(f"  有SKU图片的商品: {sku_count}")
        print(f"  有QC图片的商品: {qc_count}")
        print(f"  有商品链接的商品: {url_count}")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
