#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QC图片统计程序

功能说明：
1. 统计 findqc_local_data.db 数据库中 QC 图片的总数量
2. 统计有 QC 图的商品数量
3. 统计没有 QC 图的商品数量
4. 统计 QC 图数量分布（0张、1-5张、6-10张、11-20张、21-50张、50+张）
5. 显示统计结果的详细信息

输入：
- findqc_local_data.db：SQLite 数据库文件

输出：
- 控制台输出：统计结果报告

配置：
- DB_NAME：数据库文件名（默认 findqc_local_data.db）
"""

import sqlite3
import os

# 数据库文件名
DB_NAME = "findqc_local_data.db"


def count_qc_images():
    """
    统计数据库中的 QC 图数量
    """
    # 检查数据库文件是否存在
    if not os.path.exists(DB_NAME):
        print(f"错误: 找不到数据库文件 '{DB_NAME}'")
        return
    
    # 连接数据库
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # 1. 统计 QC 图总数（所有商品的 qc_pic_cnt 字段之和）
        cursor.execute("SELECT SUM(qc_pic_cnt) FROM products WHERE qc_pic_cnt IS NOT NULL")
        total_qc_images = cursor.fetchone()[0] or 0
        
        # 2. 统计有 QC 图的商品数量
        cursor.execute("SELECT COUNT(*) FROM products WHERE qc_pic_cnt > 0")
        products_with_qc = cursor.fetchone()[0]
        
        # 3. 统计总商品数
        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]
        
        # 4. 统计没有 QC 图的商品数量
        cursor.execute("SELECT COUNT(*) FROM products WHERE qc_pic_cnt IS NULL OR qc_pic_cnt = 0")
        products_without_qc = cursor.fetchone()[0]
        
        # 5. 统计 QC 图数量最多的前 10 个商品
        cursor.execute("""
            SELECT id, item_id, title, qc_pic_cnt 
            FROM products 
            WHERE qc_pic_cnt > 0 
            ORDER BY qc_pic_cnt DESC 
            LIMIT 10
        """)
        top_products = cursor.fetchall()
        
        # 6. 统计 QC 图数量的分布情况
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN qc_pic_cnt = 0 OR qc_pic_cnt IS NULL THEN '0张'
                    WHEN qc_pic_cnt BETWEEN 1 AND 5 THEN '1-5张'
                    WHEN qc_pic_cnt BETWEEN 6 AND 10 THEN '6-10张'
                    WHEN qc_pic_cnt BETWEEN 11 AND 20 THEN '11-20张'
                    WHEN qc_pic_cnt BETWEEN 21 AND 50 THEN '21-50张'
                    ELSE '50张以上'
                END AS range_group,
                COUNT(*) AS count
            FROM products
            GROUP BY range_group
            ORDER BY 
                CASE range_group
                    WHEN '0张' THEN 1
                    WHEN '1-5张' THEN 2
                    WHEN '6-10张' THEN 3
                    WHEN '11-20张' THEN 4
                    WHEN '21-50张' THEN 5
                    WHEN '50张以上' THEN 6
                END
        """)
        distribution = cursor.fetchall()
        
        # 打印统计结果
        print("=" * 60)
        print("QC 图统计报告")
        print("=" * 60)
        print(f"\n📊 总体统计:")
        print(f"  • QC 图总数: {total_qc_images:,} 张")
        print(f"  • 有 QC 图的商品数: {products_with_qc:,} 个")
        print(f"  • 没有 QC 图的商品数: {products_without_qc:,} 个")
        print(f"  • 总商品数: {total_products:,} 个")
        
        if total_products > 0:
            qc_coverage = (products_with_qc / total_products) * 100
            print(f"  • QC 图覆盖率: {qc_coverage:.2f}%")
        
        # 打印分布情况
        print(f"\n📈 QC 图数量分布:")
        for range_group, count in distribution:
            percentage = (count / total_products * 100) if total_products > 0 else 0
            print(f"  • {range_group}: {count:,} 个商品 ({percentage:.2f}%)")
        
        # 打印 QC 图数量最多的商品
        if top_products:
            print(f"\n🏆 QC 图数量最多的前 10 个商品:")
            for idx, (product_id, item_id, title, qc_count) in enumerate(top_products, 1):
                title_display = (title[:40] + "...") if title and len(title) > 40 else (title or "无标题")
                print(f"  {idx:2d}. 商品ID: {product_id}, QC图: {qc_count} 张")
                print(f"      标题: {title_display}")
        
        print("\n" + "=" * 60)
        
    except sqlite3.Error as e:
        print(f"数据库查询错误: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    count_qc_images()

