#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重复数据清理程序

功能说明：
1. 清除 JSON 文件中重复的 itemId 对象
2. 删除原则：保留第一个出现的，删除后续重复的
3. 支持自动备份：处理前会备份原文件为 .backup
4. 统计重复数量和处理结果
5. 支持处理大型 JSON 文件（数组格式）

输入：
- qc_timestamps.json：包含商品ID和时间戳的 JSON 文件
  格式：[{"itemId": "xxx", "timestamps": [...]}, ...]

输出：
- qc_timestamps.json：去重后的 JSON 文件（覆盖原文件）
- qc_timestamps.json.backup：原文件的备份

配置：
- INPUT_FILE：输入文件名（默认 qc_timestamps.json）
- BACKUP_FILE：备份文件名（默认 qc_timestamps.json.backup）
"""

import json
import os
from collections import OrderedDict

# --- 配置区域 ---
INPUT_FILE = "qc_timestamps.json"
BACKUP_FILE = "qc_timestamps.json.backup"
# ----------------

def remove_duplicate_itemids(input_file, backup=True):
    """
    清除 JSON 文件中重复的 itemId 对象
    删除原则：保留第一个出现的，删除后续重复的
    """
    print(f"开始处理文件: {input_file}")
    
    # 检查文件是否存在
    if not os.path.exists(input_file):
        print(f"错误: 文件 '{input_file}' 不存在")
        return
    
    # 读取 JSON 文件（使用更健壮的方式）
    print("正在读取文件...")
    try:
        # 先尝试正常读取
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查文件是否以 ] 结尾（数组格式）
        content = content.strip()
        if not content.endswith(']'):
            print("[警告] 文件可能不完整，尝试修复...")
            # 尝试修复：移除末尾不完整的对象
            last_complete_pos = content.rfind('}')
            if last_complete_pos > 0:
                after_last_obj = content[last_complete_pos + 1:].strip()
                if after_last_obj and not after_last_obj.startswith(','):
                    if not after_last_obj.startswith(']'):
                        content = content[:last_complete_pos + 1] + '\n]'
                        print("[提示] 已尝试修复文件末尾")
        
        # 解析 JSON
        data = json.loads(content)
        
    except json.JSONDecodeError as e:
        print(f"[错误] JSON 解析失败: {e}")
        print(f"[错误] 位置: 行 {e.lineno}, 列 {e.colno}")
        print(f"[提示] 文件可能在写入过程中被中断，导致格式不完整")
        
        # 尝试流式解析
        print("\n[尝试] 使用流式解析模式...")
        data = []
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                buffer = ""
                line_num = 0
                obj_start = -1
                
                for line in f:
                    line_num += 1
                    buffer += line
                    
                    # 每1000行尝试解析一次
                    if line_num % 1000 == 0:
                        try:
                            # 尝试找到最后一个完整的对象
                            last_brace = buffer.rfind('}')
                            if last_brace > 0:
                                temp_buffer = buffer[:last_brace + 1]
                                # 尝试解析
                                if temp_buffer.strip().startswith('['):
                                    parsed = json.loads(temp_buffer + ']')
                                    if isinstance(parsed, list):
                                        data = parsed
                                        print(f"  已解析到第 {line_num} 行，共 {len(data)} 条")
                        except:
                            pass
                
                # 最后尝试解析剩余内容
                if buffer:
                    try:
                        buffer = buffer.rstrip().rstrip(',')
                        if not buffer.endswith(']'):
                            buffer += '\n]'
                        parsed = json.loads(buffer)
                        if isinstance(parsed, list):
                            data = parsed
                    except:
                        pass
            
            if data:
                print(f"[成功] 流式解析完成，共读取 {len(data)} 条数据")
            else:
                print("[错误] 流式解析也失败，无法读取数据")
                return
        except Exception as e2:
            print(f"[错误] 流式解析也失败: {e2}")
            return
    except Exception as e:
        print(f"[错误] 读取文件失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return
    
    if not isinstance(data, list):
        print(f"[错误] 文件格式不正确，期望数组格式，实际: {type(data)}")
        return
    
    original_count = len(data)
    print(f"原始数据条数: {original_count}")
    
    # 验证数据完整性
    valid_count = 0
    invalid_count = 0
    for item in data:
        if isinstance(item, dict) and "itemId" in item and item.get("itemId"):
            valid_count += 1
        else:
            invalid_count += 1
    
    print(f"有效数据条数: {valid_count}")
    if invalid_count > 0:
        print(f"[警告] 无效数据条数: {invalid_count}")
    
    # 使用 OrderedDict 来保持顺序并去重
    # key: itemId, value: 对象
    seen_itemids = OrderedDict()
    duplicates = []
    
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            print(f"[警告] 第 {idx + 1} 条数据格式不正确，跳过")
            continue
        
        item_id = item.get("itemId")
        if not item_id:
            print(f"[警告] 第 {idx + 1} 条数据缺少 itemId，跳过")
            continue
        
        # 如果 itemId 已存在，记录为重复
        if item_id in seen_itemids:
            duplicates.append({
                "index": idx + 1,
                "itemId": item_id,
                "original_data": item
            })
        else:
            # 第一次出现，保留
            seen_itemids[item_id] = item
    
    duplicate_count = len(duplicates)
    print(f"发现重复项: {duplicate_count} 个")
    
    if duplicate_count == 0:
        print("没有发现重复项，文件无需处理")
        return
    
    # 显示一些重复项的示例
    if duplicate_count > 0:
        print("\n重复项示例（前10个）:")
        for dup in duplicates[:10]:
            print(f"  位置 {dup['index']}: itemId = {dup['itemId']}")
        if duplicate_count > 10:
            print(f"  ... 还有 {duplicate_count - 10} 个重复项")
    
    # 创建去重后的数据（保持顺序）
    deduplicated_data = list(seen_itemids.values())
    new_count = len(deduplicated_data)
    
    # 计算实际删除的数量（包括无效数据）
    total_removed = original_count - new_count
    duplicate_removed = duplicate_count
    invalid_removed = invalid_count
    
    print(f"\n去重后数据条数: {new_count}")
    print(f"删除统计:")
    print(f"  重复项删除: {duplicate_removed} 条")
    print(f"  无效数据删除: {invalid_removed} 条")
    print(f"  总计删除: {total_removed} 条")
    
    # 备份原文件
    if backup:
        print(f"\n正在备份原文件到: {BACKUP_FILE}")
        try:
            with open(input_file, 'r', encoding='utf-8') as src:
                with open(BACKUP_FILE, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
            print("备份完成")
        except Exception as e:
            print(f"[警告] 备份失败: {e}")
            response = input("是否继续覆盖原文件？(y/n): ")
            if response.lower() != 'y':
                print("操作已取消")
                return
    
    # 写入去重后的数据
    print(f"\n正在保存去重后的数据到: {INPUT_FILE}")
    try:
        with open(input_file, 'w', encoding='utf-8') as f:
            json.dump(deduplicated_data, f, ensure_ascii=False, indent=2)
        print("保存完成！")
        
        # 验证：重新读取文件确认
        print("\n验证结果:")
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                verify_data = json.load(f)
            verify_count = len(verify_data) if isinstance(verify_data, list) else 0
            
            print(f"  原始条数: {original_count}")
            print(f"  去重后条数: {new_count}")
            print(f"  验证读取条数: {verify_count}")
            print(f"  删除条数: {total_removed}")
            if duplicate_count > 0:
                print(f"  重复率: {duplicate_count / original_count * 100:.2f}%")
            
            if verify_count != new_count:
                print(f"  [警告] 验证失败！文件中的条数 ({verify_count}) 与预期 ({new_count}) 不一致")
            else:
                print(f"  [成功] 验证通过！")
                
            # 验证是否有重复
            verify_ids = set()
            verify_duplicates = []
            for item in verify_data:
                if isinstance(item, dict) and "itemId" in item:
                    item_id = item.get("itemId")
                    if item_id in verify_ids:
                        verify_duplicates.append(item_id)
                    else:
                        verify_ids.add(item_id)
            
            if verify_duplicates:
                print(f"  [警告] 验证发现仍有 {len(verify_duplicates)} 个重复项！")
                print(f"  前5个重复的 itemId: {verify_duplicates[:5]}")
            else:
                print(f"  [成功] 验证无重复项！")
                
        except Exception as e:
            print(f"  [错误] 验证读取失败: {e}")
        
    except Exception as e:
        print(f"错误: 保存文件失败: {e}")
        if backup and os.path.exists(BACKUP_FILE):
            print(f"可以从备份文件恢复: {BACKUP_FILE}")

def main():
    print("=" * 60)
    print("清除 qc_timestamps.json 中重复的 itemId 对象")
    print("=" * 60)
    print()
    
    remove_duplicate_itemids(INPUT_FILE, backup=True)
    
    print("\n" + "=" * 60)
    print("处理完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()


