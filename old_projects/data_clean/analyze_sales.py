#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
销售数据分析程序

功能说明：
1. 从 qc_timestamps.json 中读取商品的 QC 时间戳数据
2. 统计指定天数内（默认30天）的销量
3. 支持时间间隔归并：将指定时间间隔内（默认30秒）的多个时间戳归为一个销量
4. 支持时区配置：可设置统计时区（默认北京时间）
5. 生成销售数据 JSON 文件，格式为：
   [
     {"itemId": "xxx", "sales30": 销量},
     ...
   ]
6. 输出文件名格式：sales_{days}days_{interval}.json

输入：
- qc_timestamps.json：包含商品 itemId 和 QC 时间戳列表的数据文件

输出：
- sales_30days_30s.json：30天内、30秒间隔的销量统计文件
- 可配置生成不同天数和间隔的统计文件

配置：
- DAYS：统计近多少天的销量（默认30天）
- TIME_INTERVAL_SECONDS：时间间隔（秒），多少秒内的 time 归为一个销量（默认30秒）
- TIMEZONE：时区设置（默认 Asia/Shanghai 北京时间）
"""
import json
import os
from datetime import datetime, timedelta
import pytz

# --- 配置区域 ---
INPUT_FILE = "qc_timestamps.json"
OUTPUT_FILE_TEMPLATE = "sales_{days}days_{interval}.json"  # 输出文件名模板
TIMEZONE = "Asia/Shanghai"  # 时区：Asia/Shanghai (北京时间), UTC, America/New_York 等
DAYS = 30  # 统计近多少天的销量
TIME_INTERVAL_SECONDS = 30  # 时间间隔（秒）：多少秒内的 time 归为一个销量
# ----------------

def get_timezone(tz_name):
    """获取时区对象"""
    try:
        return pytz.timezone(tz_name)
    except Exception as e:
        print(f"[错误] 无效的时区: {tz_name}")
        print(f"[提示] 常用时区: Asia/Shanghai (北京时间), UTC, America/New_York")
        raise

def timestamp_to_datetime(timestamp_ms, tz):
    """将毫秒时间戳转换为指定时区的 datetime"""
    timestamp_s = timestamp_ms / 1000
    dt = datetime.fromtimestamp(timestamp_s, tz=tz)
    return dt

def count_sales(timestamps, time_interval_seconds):
    """
    统计销量：将时间间隔内的多个 time 归为一个销量
    返回：销量数量
    """
    if not timestamps:
        return 0
    
    # 去重并排序
    unique_timestamps = sorted(set(timestamps))
    
    if len(unique_timestamps) == 0:
        return 0
    
    # 将时间戳转换为秒（用于计算间隔）
    timestamps_seconds = [ts / 1000 for ts in unique_timestamps]
    
    # 分组：时间间隔内的归为一组
    groups = []
    current_group = [timestamps_seconds[0]]
    
    for ts in timestamps_seconds[1:]:
        # 如果当前时间戳与上一组最后一个时间戳的间隔小于等于设定值，归为同一组
        if ts - current_group[-1] <= time_interval_seconds:
            current_group.append(ts)
        else:
            # 开始新的一组
            groups.append(current_group)
            current_group = [ts]
    
    # 添加最后一组
    if current_group:
        groups.append(current_group)
    
    # 每组算一次销量
    return len(groups)

def load_existing_results(output_file):
    """
    加载已存在的结果文件，返回已处理的 itemId 集合和现有结果列表
    """
    if not os.path.exists(output_file):
        return set(), []
    
    try:
        print(f"正在检查已有结果文件: {output_file}...")
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_results = json.load(f)
        
        if not isinstance(existing_results, list):
            print("[警告] 已有结果文件格式不正确，将重新开始")
            return set(), []
        
        existing_ids = {item.get("itemId") for item in existing_results if isinstance(item, dict) and "itemId" in item}
        print(f"[断点续传] 发现已有 {len(existing_ids)} 个已处理的商品")
        
        if existing_ids:
            sample_ids = list(existing_ids)[:5]
            print(f"[断点续传] 已处理商品示例: {sample_ids}")
        
        return existing_ids, existing_results
    except json.JSONDecodeError as e:
        print(f"[警告] 读取已有结果文件失败: {e}，将重新开始")
        return set(), []
    except Exception as e:
        print(f"[警告] 读取已有结果文件失败: {type(e).__name__}: {e}，将重新开始")
        return set(), []

def generate_output_filename(days, time_interval_seconds):
    """
    根据参数生成输出文件名
    例如：sales_30days_1s.json, sales_30days_60s.json, sales_30days_300s.json
    """
    # 格式化时间间隔：直接使用秒数，例如 1 -> 1s, 60 -> 60s, 300 -> 300s
    interval_str = f"{int(time_interval_seconds)}s"
    
    filename = OUTPUT_FILE_TEMPLATE.format(
        days=days,
        interval=interval_str
    )
    return filename

def filter_recent_sales(input_file, output_file, timezone_name, days, time_interval_seconds):
    """
    筛选近 N 天内有 time 的商品，并统计销量
    支持断点续传：从已有结果继续处理
    """
    print("=" * 60)
    print("筛选近30天销量数据")
    print("=" * 60)
    print(f"输入文件: {input_file}")
    print(f"输出文件: {output_file}")
    print(f"时区: {timezone_name}")
    print(f"统计天数: {days} 天")
    print(f"时间间隔: {time_interval_seconds} 秒")
    print("=" * 60)
    print()
    
    # 加载已有结果，实现断点续传
    existing_ids, existing_results = load_existing_results(output_file)
    print()
    
    # 检查输入文件
    if not os.path.exists(input_file):
        print(f"[错误] 文件不存在: {input_file}")
        return
    
    # 获取时区
    tz = get_timezone(timezone_name)
    
    # 计算时间范围
    now = datetime.now(tz)
    start_time = now - timedelta(days=days)
    start_timestamp_ms = int(start_time.timestamp() * 1000)
    
    print(f"当前时间 ({timezone_name}): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"统计起始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"时间戳范围: >= {start_timestamp_ms}")
    print()
    
    # 读取 JSON 文件（使用更健壮的方式处理大文件和不完整文件）
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
            # 找到最后一个完整的对象
            last_complete_pos = content.rfind('}')
            if last_complete_pos > 0:
                # 找到最后一个 } 后面的内容
                after_last_obj = content[last_complete_pos + 1:].strip()
                # 如果后面还有内容但不是 ], 说明文件不完整
                if after_last_obj and not after_last_obj.startswith(','):
                    # 尝试添加 ]
                    if not after_last_obj.startswith(']'):
                        content = content[:last_complete_pos + 1] + '\n]'
                        print("[提示] 已尝试修复文件末尾")
        
        # 解析 JSON
        data = json.loads(content)
        
    except json.JSONDecodeError as e:
        print(f"[错误] JSON 解析失败: {e}")
        print(f"[错误] 位置: 行 {e.lineno}, 列 {e.colno}")
        print(f"[提示] 文件可能在写入过程中被中断，导致格式不完整")
        print(f"[提示] 建议：1) 检查文件是否完整 2) 使用 remove_duplicates.py 修复文件")
        
        # 尝试流式解析：逐行读取，跳过有问题的部分
        print("\n[尝试] 使用流式解析模式...")
        data = []
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                buffer = ""
                brace_count = 0
                in_string = False
                escape_next = False
                line_num = 0
                
                for line in f:
                    line_num += 1
                    buffer += line
                    
                    # 简单检查：如果遇到完整的对象就解析
                    if line.strip().startswith('{') and '}' in line:
                        try:
                            # 尝试解析这一行
                            obj = json.loads(line.strip().rstrip(','))
                            if isinstance(obj, dict) and "itemId" in obj:
                                data.append(obj)
                        except:
                            pass
                    
                    # 每1000行尝试解析一次缓冲区
                    if line_num % 1000 == 0:
                        try:
                            # 尝试解析当前缓冲区
                            parsed = json.loads(buffer.rstrip().rstrip(',') + ']')
                            if isinstance(parsed, list):
                                data = parsed
                                buffer = ""
                                print(f"  已解析到第 {line_num} 行")
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
        print(f"[错误] 文件格式不正确，期望数组格式")
        return
    
    print(f"共读取 {len(data)} 条商品数据")
    print()
    
    # 筛选和统计
    print("正在筛选和统计...")
    new_results = []  # 新处理的结果
    total_items = len(data)
    processed = 0
    filtered_count = 0
    skipped_count = 0  # 跳过的已处理商品
    no_time_count = 0
    out_of_range_count = 0
    
    for item in data:
        processed += 1
        
        if not isinstance(item, dict):
            continue
        
        item_id = item.get("itemId")
        times = item.get("time", [])
        
        if not item_id:
            continue
        
        item_id_str = str(item_id)
        
        # 断点续传：如果已处理过，跳过
        if item_id_str in existing_ids:
            skipped_count += 1
            continue
        
        # 如果没有 time 字段或为空，跳过
        if not times or not isinstance(times, list):
            no_time_count += 1
            continue
        
        # 筛选出在时间范围内的 time
        recent_times = [t for t in times if isinstance(t, (int, float)) and t >= start_timestamp_ms]
        
        # 如果没有在时间范围内的 time，跳过
        if not recent_times:
            out_of_range_count += 1
            continue
        
        # 统计销量（去重：时间间隔内的归为一个）
        sales_count = count_sales(recent_times, time_interval_seconds)
        
        if sales_count > 0:
            new_results.append({
                "itemId": item_id_str,
                "sales30": sales_count
            })
            filtered_count += 1
        
        # 进度显示
        if processed % 1000 == 0:
            print(f"  进度: {processed}/{total_items} (已筛选: {filtered_count}, 跳过: {skipped_count})")
    
    print()
    print("=" * 60)
    print("统计结果:")
    print("=" * 60)
    print(f"总商品数: {total_items}")
    print(f"已跳过（已处理）: {skipped_count}")
    print(f"无 time 字段: {no_time_count}")
    print(f"时间范围外: {out_of_range_count}")
    print(f"本次新增: {filtered_count}")
    print()
    
    # 合并已有结果和新结果
    if existing_results:
        print(f"[合并] 合并已有结果 ({len(existing_results)} 条) 和新结果 ({len(new_results)} 条)...")
        # 创建已有结果的 itemId 到结果的映射
        existing_map = {item["itemId"]: item for item in existing_results if isinstance(item, dict) and "itemId" in item}
        
        # 更新或添加新结果
        for new_item in new_results:
            item_id = new_item["itemId"]
            existing_map[item_id] = new_item
        
        # 合并为列表
        all_results = list(existing_map.values())
        print(f"[合并] 合并后共 {len(all_results)} 条数据")
    else:
        all_results = new_results
        print(f"[新增] 共 {len(all_results)} 条新数据")
    
    print()
    
    # 按销量排序
    all_results.sort(key=lambda x: x["sales30"], reverse=True)
    
    # 显示销量统计
    if all_results:
        total_sales = sum(item["sales30"] for item in all_results)
        avg_sales = total_sales / len(all_results)
        max_sales = max(item["sales30"] for item in all_results)
        min_sales = min(item["sales30"] for item in all_results)
        
        print("销量统计（总计）:")
        print(f"  总商品数: {len(all_results)}")
        print(f"  总销量: {total_sales}")
        print(f"  平均销量: {avg_sales:.2f}")
        print(f"  最高销量: {max_sales}")
        print(f"  最低销量: {min_sales}")
        print()
        
        # 显示销量前10的商品
        print("销量前10的商品:")
        for idx, item in enumerate(all_results[:10], 1):
            print(f"  {idx}. itemId: {item['itemId']}, 销量: {item['sales30']}")
        print()
    
    # 保存结果
    print(f"正在保存结果到: {output_file}...")
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"保存成功！共 {len(all_results)} 条数据")
        if new_results:
            print(f"本次新增: {len(new_results)} 条")
    except Exception as e:
        print(f"[错误] 保存文件失败: {e}")
        return
    
    print("=" * 60)
    print("处理完成！")
    print("=" * 60)

def main():
    # 根据参数生成输出文件名
    output_file = generate_output_filename(DAYS, TIME_INTERVAL_SECONDS)
    
    filter_recent_sales(
        input_file=INPUT_FILE,
        output_file=output_file,
        timezone_name=TIMEZONE,
        days=DAYS,
        time_interval_seconds=TIME_INTERVAL_SECONDS
    )

if __name__ == "__main__":
    main()

