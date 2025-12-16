#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QC时间戳抓取程序

功能说明：
1. 从 findqc.com API 获取商品的 QC 时间戳数据
2. 读取 goods_data_tree 目录下的商品数据文件，提取商品ID列表
3. 调用 detail 接口获取每个商品的 QC 时间戳信息
4. 支持高并发处理（默认50个线程）
5. 支持断点续传：中断后重新运行会跳过已处理的商品
6. 批量保存机制：每处理 N 个商品后自动保存到 qc_timestamps.json
7. 支持中断保护：Ctrl+C 时会安全保存进度

输入：
- goods_data_tree/：包含商品数据的目录（从 fetch_product_ids.py 生成）

输出：
- qc_timestamps.json：包含商品ID和QC时间戳列表的 JSON 文件
  格式：[{"itemId": "xxx", "timestamps": [时间戳1, 时间戳2, ...]}, ...]

配置：
- GOODS_DATA_DIR：商品数据目录（默认 goods_data_tree）
- OUTPUT_FILE：输出文件名（默认 qc_timestamps.json）
- MAX_WORKERS：并发线程数（默认50）
- BUFFER_SIZE：缓冲池大小（默认100）
- MAX_RETRIES：最大重试次数（默认5）
- REQUEST_INTERVAL：请求间隔（默认0.005秒）
"""

import os
import json
import requests
import time
import random
import threading
import signal
import atexit
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置区域 ---
GOODS_DATA_DIR = "goods_data_tree"
OUTPUT_FILE = "qc_timestamps.json"
BASE_URL = "https://findqc.com/api/goods/detail"
MAX_WORKERS = 50  # 增加并发线程数（学习 main.py 的高并发方式）
BUFFER_SIZE = 100  # 缓冲池大小，满 100 个就写入（增加以减少保存频率）
MAX_RETRIES = 5  # 最大重试次数
RETRY_DELAY = 1  # 重试延时（秒）
LOG_SAVE_INTERVAL = 20  # 每保存多少次才输出一次日志（减少日志输出）
REQUEST_INTERVAL = 0.005  # 每个请求之间的最小间隔（秒），用于均匀分布请求
# ----------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

# 线程锁，用于保护文件写入和缓冲池操作
file_lock = threading.Lock()
buffer_lock = threading.Lock()
request_lock = threading.Lock()  # 请求速率控制锁

# 缓冲池
result_buffer = []
processed_count = 0
failed_count = 0
shutdown_flag = threading.Event()  # 用于标记程序是否正在关闭
save_count = 0  # 保存次数计数器（用于控制日志输出频率）

# 请求速率控制：记录上次请求时间
last_request_time = time.time()
request_count = 0  # 请求计数器

def extract_item_ids_from_json(filepath):
    """
    从 JSON 文件中提取所有商品的 itemId 和 mallType
    返回: [(itemId, mallType), ...]
    """
    items = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        # 根据结构：data -> data -> 商品列表
        outer_data = content.get('data', {})
        if not isinstance(outer_data, dict):
            return items
        
        product_list = outer_data.get('data', [])
        if not isinstance(product_list, list):
            return items
        
        for item in product_list:
            item_id = item.get('itemId')
            mall_type = item.get('mallType')
            if item_id and mall_type:
                items.append((str(item_id), mall_type))
    
    except Exception as e:
        print(f"[错误] 解析文件 {filepath} 失败: {e}")
    
    return items

def rate_limit():
    """
    请求速率限制：确保请求在时间上均匀分布
    使用全局锁和上次请求时间来控制请求间隔
    """
    global last_request_time, request_count
    
    with request_lock:
        current_time = time.time()
        elapsed = current_time - last_request_time
        
        # 如果距离上次请求时间太短，需要等待
        if elapsed < REQUEST_INTERVAL:
            sleep_time = REQUEST_INTERVAL - elapsed
            time.sleep(sleep_time)
            current_time = time.time()
        
        # 更新上次请求时间
        last_request_time = current_time
        request_count += 1
        
        # 添加小的随机抖动，避免完全同步
        jitter = random.uniform(0, REQUEST_INTERVAL * 0.1)
        time.sleep(jitter)

def fetch_qc_timestamps(item_id, mall_type):
    """
    获取商品详情并提取 qcList 中的所有 time 字段
    返回: [time1, time2, ...] 或 None（如果请求失败）
    学习 main.py 的方式：直接使用 requests.get，减少延时
    添加重试机制处理网络错误
    添加请求速率限制，确保请求均匀分布
    """
    # 请求速率限制：确保请求在时间上均匀分布
    rate_limit()
    
    params = {
        "itemId": item_id,
        "mallType": mall_type,
        "currencyType": "USD",
        "langType": "en",
        "notNeedQc": "true"
    }
    
    # 重试机制
    for attempt in range(MAX_RETRIES):
        try:
            # 学习 main.py：直接使用 requests.get，不使用 Session
            response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=10)
            
            if response.status_code != 200:
                if attempt < MAX_RETRIES - 1:
                    print(f"[!] itemId:{item_id} 请求失败 code:{response.status_code}，重试 {attempt + 1}/{MAX_RETRIES}")
                    time.sleep(RETRY_DELAY * (attempt + 1))  # 递增延时
                    continue
                else:
                    print(f"[!] itemId:{item_id} 请求失败 code:{response.status_code}，已重试 {MAX_RETRIES} 次")
                    return None
            
            # 成功获取响应
            res_json = response.json()
            
            # 提取 qcList 中的 time 字段
            # 根据 API 响应结构：data -> data -> qcList
            data_root = res_json.get("data", {})
            inner_data = data_root.get("data", {})
            qc_list = inner_data.get("qcList", [])
            
            timestamps = []
            for qc in qc_list:
                qc_time = qc.get("time")
                if qc_time is not None:
                    timestamps.append(qc_time)
            
            # 即使为空列表也返回，表示成功获取但无时间戳
            return timestamps
        
        except (requests.exceptions.ConnectionError, 
                requests.exceptions.Timeout,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectTimeout,
                requests.exceptions.RequestException,
                OSError,  # 包含 ConnectionResetError, ConnectionAbortedError 等
                ConnectionResetError,
                ConnectionAbortedError) as e:
            # 网络相关错误，可以重试
            if attempt < MAX_RETRIES - 1:
                retry_delay = RETRY_DELAY * (attempt + 1)  # 递增延时：1s, 2s, 3s
                error_name = type(e).__name__
                print(f"[重试] itemId:{item_id} 网络错误: {error_name}，{retry_delay}秒后重试 {attempt + 1}/{MAX_RETRIES}")
                time.sleep(retry_delay)
                continue
            else:
                error_name = type(e).__name__
                print(f"[错误] itemId:{item_id} 获取失败（已重试 {MAX_RETRIES} 次）: {error_name}")
                return None
        
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # 数据解析错误，不重试（重试也没用）
            print(f"[错误] itemId:{item_id} 数据解析失败: {e}")
            return None
        
        except Exception as e:
            # 其他未知错误，尝试重试
            if attempt < MAX_RETRIES - 1:
                retry_delay = RETRY_DELAY * (attempt + 1)
                print(f"[重试] itemId:{item_id} 未知错误: {type(e).__name__}，{retry_delay}秒后重试 {attempt + 1}/{MAX_RETRIES}")
                time.sleep(retry_delay)
                continue
            else:
                print(f"[错误] itemId:{item_id} 获取失败（已重试 {MAX_RETRIES} 次）: {e}")
                return None
    
    return None

def load_existing_data():
    """
    加载已存在的 JSON 文件，返回已处理的 itemId 集合和最后一个 itemId
    使用安全加载，如果文件损坏会自动修复
    """
    if not os.path.exists(OUTPUT_FILE):
        return set(), None, []
    
    try:
        print(f"正在读取文件: {OUTPUT_FILE}...")
        existing_data = safe_load_json(OUTPUT_FILE)
        
        if not existing_data:
            print("[提示] 文件为空或无法读取")
            return set(), None, []
        
        existing_ids = set()
        last_item_id = None
        result_list = []
        invalid_count = 0
        
        # 处理数据
        print(f"[提示] 检测到数据，共 {len(existing_data)} 条")
        for idx, item in enumerate(existing_data):
            if isinstance(item, dict) and "itemId" in item:
                item_id = item.get("itemId")
                if item_id:
                    item_id_str = str(item_id)
                    existing_ids.add(item_id_str)
                    result_list.append(item)
                    last_item_id = item_id_str
                else:
                    invalid_count += 1
            else:
                invalid_count += 1
                if idx < 10:  # 只显示前10个无效数据的警告
                    print(f"[警告] 第 {idx + 1} 条数据格式不正确: {type(item)}")
        
        if invalid_count > 0:
            print(f"[警告] 发现 {invalid_count} 条无效数据")
        
        print(f"[成功] 成功读取 {len(existing_ids)} 个已处理的 itemId")
        return existing_ids, last_item_id, result_list
    except Exception as e:
        print(f"[错误] 读取已有文件失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return set(), None, []

def append_to_file(item_id, timestamps):
    """线程安全地追加数据到 JSON 文件"""
    global result_buffer, processed_count
    
    with buffer_lock:
        result_buffer.append((item_id, timestamps))
        processed_count += 1
        
        # 缓冲池满 5 个就写入文件
        if len(result_buffer) >= BUFFER_SIZE:
            flush_buffer()

def safe_load_json(filepath):
    """
    安全地加载 JSON 文件，如果文件不完整或格式错误，尝试修复
    """
    if not os.path.exists(filepath):
        return []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        if not content:
            return []
        
        # 尝试正常解析
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # 旧格式转换
                return [{"itemId": k, "time": v} for k, v in data.items()]
            return []
        except json.JSONDecodeError:
            # JSON 格式错误，尝试修复
            print(f"[修复] 检测到 JSON 格式错误，尝试修复...")
            
            # 尝试找到最后一个完整的对象
            last_brace = content.rfind('}')
            if last_brace > 0:
                # 找到最后一个 } 前面的内容
                fixed_content = content[:last_brace + 1]
                # 检查是否以 [ 开头
                if fixed_content.strip().startswith('['):
                    # 尝试添加 ]
                    if not fixed_content.rstrip().endswith(']'):
                        fixed_content = fixed_content.rstrip().rstrip(',') + '\n]'
                    try:
                        data = json.loads(fixed_content)
                        if isinstance(data, list):
                            print(f"[修复] 成功修复，保留了 {len(data)} 条数据")
                            return data
                    except:
                        pass
            
            # 如果修复失败，尝试从备份恢复
            backup_file = filepath + '.backup'
            if os.path.exists(backup_file):
                print(f"[修复] 尝试从备份文件恢复: {backup_file}")
                try:
                    with open(backup_file, 'r', encoding='utf-8') as f:
                        backup_data = json.load(f)
                    if isinstance(backup_data, list):
                        print(f"[修复] 从备份恢复成功，共 {len(backup_data)} 条数据")
                        return backup_data
                except:
                    pass
            
            print(f"[错误] 无法修复 JSON 文件，返回空列表")
            return []
    except Exception as e:
        print(f"[错误] 读取文件失败: {e}")
        return []

def flush_buffer(force=False):
    """
    将缓冲池中的数据写入文件（线程安全），使用原子写入（临时文件+重命名）
    force: 是否强制写入（即使缓冲池为空也执行检查）
    """
    global result_buffer, save_count
    
    if not result_buffer and not force:
        return
    
    if not result_buffer:
        return
    
    buffer_size = len(result_buffer)
    save_count += 1
    should_log = (save_count % LOG_SAVE_INTERVAL == 0) or force
    
    if should_log:
        print(f"[保存] 正在保存 {buffer_size} 条数据到文件...")
    
    with file_lock:
        try:
            # 读取现有数据（使用安全加载）
            existing_list = safe_load_json(OUTPUT_FILE)
            
            # 创建 itemId 到索引的映射，用于去重
            existing_ids_map = {item["itemId"]: idx for idx, item in enumerate(existing_list) if isinstance(item, dict) and "itemId" in item}
            
            # 添加新数据（去重：如果已存在则更新，否则追加）
            added_count = 0
            updated_count = 0
            for item_id, timestamps in result_buffer:
                if item_id in existing_ids_map:
                    # 更新已存在的记录
                    existing_list[existing_ids_map[item_id]]["time"] = timestamps
                    updated_count += 1
                else:
                    # 追加新记录
                    existing_list.append({"itemId": item_id, "time": timestamps})
                    added_count += 1
            
            # 原子写入：先写入临时文件，成功后再替换
            temp_file = OUTPUT_FILE + '.tmp'
            backup_file = OUTPUT_FILE + '.backup'
            
            # 1. 先备份原文件（每100次保存备份一次）
            if save_count % 100 == 0 and os.path.exists(OUTPUT_FILE):
                try:
                    import shutil
                    shutil.copy2(OUTPUT_FILE, backup_file)
                except:
                    pass
            
            # 2. 写入临时文件
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(existing_list, f, ensure_ascii=False, indent=2)
                # 确保数据完整写入（刷新到磁盘）
                f.flush()
                os.fsync(f.fileno())
            
            # 3. 原子替换：重命名临时文件为正式文件
            if os.path.exists(OUTPUT_FILE):
                os.replace(temp_file, OUTPUT_FILE)
            else:
                os.rename(temp_file, OUTPUT_FILE)
            
            if should_log:
                print(f"[保存] 成功保存！新增: {added_count}, 更新: {updated_count}, 总计: {len(existing_list)} 条")
            
            # 清空缓冲池（只有在成功写入后才清空）
            buffer_to_clear = result_buffer[:]
            result_buffer = []
            
        except Exception as e:
            print(f"[错误] 保存文件失败: {e}")
            import traceback
            traceback.print_exc()
            # 清理临时文件
            temp_file = OUTPUT_FILE + '.tmp'
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            # 不清空缓冲池，以便重试

def process_item(item_id, mall_type):
    """处理单个商品，直接写入缓冲池"""
    # 检查是否正在关闭
    if shutdown_flag.is_set():
        return False
    
    timestamps = fetch_qc_timestamps(item_id, mall_type)
    if timestamps is not None:  # 包括空列表的情况
        append_to_file(item_id, timestamps)
        return True
    else:
        global failed_count
        with buffer_lock:
            failed_count += 1
        return False

def cleanup_and_save():
    """清理函数：在程序退出前保存缓冲池中的数据"""
    global result_buffer
    
    if shutdown_flag.is_set():
        return  # 已经处理过了
    
    shutdown_flag.set()
    print("\n[清理] 检测到程序退出，正在保存剩余数据...")
    
    with buffer_lock:
        if result_buffer:
            print(f"[清理] 缓冲池中还有 {len(result_buffer)} 条数据未保存")
            flush_buffer(force=True)
        else:
            print("[清理] 缓冲池已为空，无需保存")
    
    print("[清理] 清理完成")

def signal_handler(signum, frame):
    """信号处理函数：处理 Ctrl+C 等中断信号"""
    print(f"\n[中断] 收到信号 {signum}，正在安全退出...")
    cleanup_and_save()
    sys.exit(0)

def main():
    # 注册信号处理和退出清理函数
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill 命令
    atexit.register(cleanup_and_save)  # 正常退出时也会执行
    
    # 清理可能存在的临时文件（之前中断留下的）
    temp_file = OUTPUT_FILE + '.tmp'
    if os.path.exists(temp_file):
        print(f"[清理] 发现临时文件，正在清理...")
        try:
            os.remove(temp_file)
            print(f"[清理] 临时文件已清理")
        except Exception as e:
            print(f"[警告] 清理临时文件失败: {e}")
    
    print("开始遍历 goods_data_tree 目录...")
    
    # 加载已存在的数据，实现断点续传
    existing_ids, last_item_id, existing_list = load_existing_data()
    if existing_ids:
        print(f"发现已有数据，已处理 {len(existing_ids)} 个商品")
        if last_item_id:
            print(f"最后一个处理的 itemId: {last_item_id}")
        # 显示一些示例 itemId
        sample_ids = list(existing_ids)[:5]
        print(f"已处理商品示例: {sample_ids}")
    
    # 收集所有 itemId 和 mallType
    all_items = []
    
    if not os.path.exists(GOODS_DATA_DIR):
        print(f"错误: 找不到目录 '{GOODS_DATA_DIR}'")
        return
    
    # 遍历所有 JSON 文件
    for root, dirs, files in os.walk(GOODS_DATA_DIR):
        for file in files:
            if file.endswith(".json"):
                filepath = os.path.join(root, file)
                items = extract_item_ids_from_json(filepath)
                all_items.extend(items)
    
    print(f"共找到 {len(all_items)} 个商品")
    
    if not all_items:
        print("没有找到任何商品数据")
        return
    
    # 去重（同一个 itemId 可能出现在多个文件中），保持顺序
    unique_items_list = []
    seen_ids = set()
    for item_id, mall_type in all_items:
        if item_id not in seen_ids:
            unique_items_list.append((item_id, mall_type))
            seen_ids.add(item_id)
    
    print(f"去重后共 {len(unique_items_list)} 个唯一商品")
    
    # 过滤掉已处理的商品，实现断点续传
    # 只使用 existing_ids 来判断，移除 skip_until_last 逻辑（可能导致问题）
    items_to_process = []
    skipped_count = 0
    
    for item_id, mall_type in unique_items_list:
        # 如果已存在，跳过
        if item_id in existing_ids:
            skipped_count += 1
            continue
        
        items_to_process.append((item_id, mall_type))
    
    print(f"已跳过 {skipped_count} 个已处理的商品")
    
    if not items_to_process:
        print("所有商品都已处理完成！")
        # 验证一下：检查是否真的所有商品都已处理
        unique_item_ids = {item_id for item_id, _ in unique_items_list}
        if len(existing_ids) != len(unique_item_ids):
            print(f"[警告] 数据不一致！已处理: {len(existing_ids)}, 总商品数: {len(unique_item_ids)}")
            missing = unique_item_ids - existing_ids
            if missing:
                print(f"[警告] 发现 {len(missing)} 个未处理的商品，但被跳过了。可能是数据源变化。")
                print(f"[提示] 前10个未处理的商品: {list(missing)[:10]}")
        return
    
    print(f"需要处理 {len(items_to_process)} 个新商品")
    
    # 使用线程池并发处理（学习 main.py 的高并发方式）
    global processed_count, failed_count
    processed_count = 0
    failed_count = 0
    total_items = len(items_to_process)
    last_save_time = time.time()
    AUTO_SAVE_INTERVAL = 30  # 每30秒自动保存一次
    
    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(process_item, item_id, mall_type): item_id 
                for item_id, mall_type in items_to_process
            }
            
            for future in as_completed(futures):
                # 检查是否正在关闭
                if shutdown_flag.is_set():
                    print("[中断] 收到退出信号，停止处理新任务...")
                    break
                
                item_id = futures[future]
                try:
                    future.result()
                    
                    # 进度显示（学习 main.py 的简洁方式）
                    with buffer_lock:
                        total_processed = processed_count + failed_count
                        if total_processed % 50 == 0:
                            print(f"进度: {total_processed}/{total_items} (成功: {processed_count}, 失败: {failed_count})")
                        
                        # 定期自动保存（即使缓冲池未满）
                        current_time = time.time()
                        if current_time - last_save_time >= AUTO_SAVE_INTERVAL and result_buffer:
                            if len(result_buffer) >= 10:  # 只有缓冲池有一定数据时才保存
                                flush_buffer(force=True)
                                last_save_time = current_time
                    
                    # 请求速率限制已经在 fetch_qc_timestamps 中处理，这里不需要额外延时
                
                except Exception as e:
                    print(f"[异常] itemId:{item_id} 处理异常: {e}")
                    with buffer_lock:
                        failed_count += 1
    except KeyboardInterrupt:
        print("\n[中断] 收到键盘中断信号")
        cleanup_and_save()
        sys.exit(0)
    except Exception as e:
        print(f"\n[错误] 发生未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        cleanup_and_save()
        raise
    
    # 最后刷新缓冲池，确保所有数据都写入
    print("\n[完成] 处理完成，正在保存剩余数据...")
    flush_buffer(force=True)
    
    # 最终统计
    with file_lock:
        if os.path.exists(OUTPUT_FILE):
            try:
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    final_data = json.load(f)
                    # 兼容新旧格式
                    if isinstance(final_data, dict):
                        final_count = len(final_data)
                    elif isinstance(final_data, list):
                        final_count = len(final_data)
                    else:
                        final_count = 0
            except:
                final_count = 0
        else:
            final_count = 0
    
    print(f"\n处理完成！本次成功: {processed_count}, 失败: {failed_count}")
    print(f"总计保存 {final_count} 个商品的时间戳数据到 {OUTPUT_FILE}")
    
    # 验证数据完整性
    expected_total = len(unique_items_list)
    actual_total = final_count
    if expected_total != actual_total:
        print(f"[警告] 数据条数不匹配！期望: {expected_total}, 实际: {actual_total}, 差异: {expected_total - actual_total}")
    else:
        print(f"[验证] 数据条数匹配！共 {actual_total} 条")

if __name__ == "__main__":
    main()

