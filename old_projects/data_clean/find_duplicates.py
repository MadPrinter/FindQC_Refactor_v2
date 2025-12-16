#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重复 ID 查找工具

功能说明：
1. 分析 JSON 数据文件中的重复 ID
2. 支持分析多个数据文件（在 config.py 中配置）
3. 支持不同的 ID 字段名（如 "id" 或 "itemId"）
4. 统计每个 ID 的出现次数
5. 生成重复 ID 报告，包含：
   - 总记录数
   - 唯一 ID 数
   - 重复的 ID 数
   - 重复次数最多的前 10 个 ID
6. 输出 JSON 文件，格式为：
   [
     {"id": "xxx", "重复次数": 2},
     ...
   ]

输入：
- 在 config.py 的 DUPLICATE_ANALYSIS_FILES 中配置的文件列表
- 默认分析：cleaned_data.json（使用 "id" 字段）
- 默认分析：sales_30days_30s.json（使用 "itemId" 字段）

输出：
- duplicate_ids_cleaned_data.json：cleaned_data.json 的重复 ID 分析结果
- duplicate_ids_sales_30days_30s.json：sales_30days_30s.json 的重复 ID 分析结果

配置：
- 所有分析文件配置在 config.py 的 DUPLICATE_ANALYSIS_FILES 中
- 每个配置包含：文件路径、ID 字段名、输出文件路径
"""

import json
from collections import Counter
from pathlib import Path
import config


def find_duplicate_ids(input_file: Path, output_file: Path, id_field: str = "id", data_name: str = ""):
    """
    查找重复的 id 并生成报告
    
    Args:
        input_file: 输入的 JSON 文件路径
        output_file: 输出的 JSON 文件路径
        id_field: ID 字段名（默认为 "id"）
        data_name: 数据名称（用于显示）
    """
    print("=" * 60)
    if data_name:
        print(f"开始分析: {data_name}")
    print("开始读取数据...")
    print("=" * 60)
    
    # 读取 JSON 文件
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"错误: 文件 {input_file} 不存在")
        return False
    
    # 打印数据源路径
    print(f"数据源: {input_path.absolute()}")
    print(f"ID 字段: {id_field}")
    
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"读取了 {len(data)} 条记录")
    
    # 统计每个 id 出现的次数
    print("\n统计 id 出现次数...")
    id_counter = Counter()
    
    for record in data:
        record_id = record.get(id_field, '')
        if record_id:
            id_counter[str(record_id)] += 1
    
    # 找出重复的 id（出现次数 > 1）
    duplicates = {id: count for id, count in id_counter.items() if count > 1}
    
    print(f"\n统计结果:")
    print(f"  总记录数: {len(data)}")
    print(f"  唯一 id 数: {len(id_counter)}")
    print(f"  重复的 id 数: {len(duplicates)}")
    
    if duplicates:
        total_duplicate_records = sum(duplicates.values())
        print(f"  重复记录总数: {total_duplicate_records}")
        print(f"  平均每个重复 id 出现次数: {total_duplicate_records / len(duplicates):.2f}")
        
        # 显示重复次数最多的前 10 个
        sorted_duplicates = sorted(duplicates.items(), key=lambda x: x[1], reverse=True)
        print(f"\n重复次数最多的前 10 个 id:")
        for i, (id, count) in enumerate(sorted_duplicates[:10], 1):
            print(f"  {i}. {id_field}={id}, 重复次数={count}")
    else:
        print("  没有发现重复的 id")
    
    # 生成输出 JSON
    print("\n" + "=" * 60)
    print("生成输出文件...")
    print("=" * 60)
    
    # 按照用户要求的格式生成：数组，每个元素是 {id: "", 重复次数: }
    output_data = [
        {"id": str(id), "重复次数": count}
        for id, count in sorted(duplicates.items(), key=lambda x: x[1], reverse=True)
    ]
    
    output_path = Path(output_file)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"成功生成文件: {output_file}")
    print(f"包含 {len(output_data)} 个重复的 id")
    if output_path.exists():
        print(f"文件大小: {output_path.stat().st_size / 1024:.2f} KB")
    
    return True


def analyze_all_files():
    """分析配置中的所有文件"""
    print("\n" + "=" * 60)
    print("重复 ID 分析工具")
    print("=" * 60)
    print(f"共需要分析 {len(config.DUPLICATE_ANALYSIS_FILES)} 个文件\n")
    
    success_count = 0
    for i, file_config in enumerate(config.DUPLICATE_ANALYSIS_FILES, 1):
        print(f"\n{'=' * 60}")
        print(f"分析文件 {i}/{len(config.DUPLICATE_ANALYSIS_FILES)}")
        print(f"{'=' * 60}\n")
        
        success = find_duplicate_ids(
            input_file=file_config['file'],
            output_file=file_config['output'],
            id_field=file_config['id_field'],
            data_name=file_config['name']
        )
        
        if success:
            success_count += 1
        
        if i < len(config.DUPLICATE_ANALYSIS_FILES):
            print("\n")
    
    print("\n" + "=" * 60)
    print("分析完成")
    print("=" * 60)
    print(f"成功分析: {success_count}/{len(config.DUPLICATE_ANALYSIS_FILES)} 个文件")


if __name__ == "__main__":
    analyze_all_files()

