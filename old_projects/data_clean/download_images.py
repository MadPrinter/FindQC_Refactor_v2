#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片下载程序

功能说明：
1. 从 cleaned_data.json 中读取商品数据，提取所有图片 URL（主图、SKU图、QC图）
2. 并发下载图片到本地目录（downloaded_images/main/, downloaded_images/sku/, downloaded_images/qc/）
3. 生成 download_mapping.json 映射文件，包含：
   - itemId：商品ID
   - imageList：本地图片路径列表
   - imageUrlList：对应的原始图片 URL 列表
4. 支持断点续传：中断后重新运行会跳过已下载的图片
5. 支持中断保护：Ctrl+C 时会安全保存进度，避免数据丢失
6. 支持图片压缩：可配置压缩模式和图片质量（节省存储空间和 API token）
7. 批量保存机制：每处理 N 个商品后自动保存映射文件

输入：
- cleaned_data.json：商品数据文件（包含图片 URL）

输出：
- downloaded_images/：本地图片存储目录
- download_mapping.json：图片路径和 URL 的映射文件

配置：
- 所有配置参数在 config.py 中
- 包括并发数、超时时间、重试次数、压缩模式等
"""

import json
import os
import time
import hashlib
import threading
import signal
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError, CancelledError
from urllib.parse import urlparse
import requests
import urllib3
from PIL import Image
import io

# 禁用 SSL 警告（因为我们设置了 verify=False）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import config

# 全局统计
_download_stats = {
    'success': 0,
    'failed': 0,
    'skipped': 0,
    '403_errors': 0
}

# 线程锁（用于保护共享数据）
_mapping_lock = threading.Lock()
_save_lock = threading.Lock()

# 中断保护相关
_shutdown_flag = threading.Event()  # 用于标记是否收到中断信号
_shutdown_count = 0  # 信号触发计数器，用于防止重复触发
_shutdown_lock = threading.Lock()  # 保护信号计数器
_pending_items = []  # 未完成的任务列表
_pending_items_lock = threading.Lock()  # 保护未完成任务列表


def get_image_extension(url: str, default: str = 'jpg') -> str:
    """
    从 URL 中提取图片扩展名
    
    Args:
        url: 图片 URL
        default: 默认扩展名
        
    Returns:
        图片扩展名（不含点号）
    """
    parsed = urlparse(url)
    path = parsed.path
    
    # 尝试从路径中提取扩展名
    if '.' in path:
        ext = path.split('.')[-1].lower()
        # 过滤掉常见的非图片扩展名
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg']:
            return ext
    
    return default


def generate_image_filename(url: str, item_id: str, image_type: str, index: int) -> str:
    """
    生成图片文件名
    
    Args:
        url: 图片 URL
        item_id: 商品 itemId
        image_type: 图片类型（main/sku/qc）
        index: 图片索引
        
    Returns:
        文件名
    """
    # 使用 URL 的哈希值作为唯一标识，避免文件名冲突
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:8]
    ext = get_image_extension(url)
    
    # 文件名格式: {itemId}_{imageType}_{index}_{hash}.{ext}
    filename = f"{item_id}_{image_type}_{index}_{url_hash}.{ext}"
    return filename


def get_headers_for_url(url: str) -> Dict[str, str]:
    """
    根据 URL 域名返回合适的请求头
    
    Args:
        url: 图片 URL
        
    Returns:
        请求头字典
    """
    headers = config.DOWNLOAD_HEADERS.copy()
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    # 针对不同域名设置不同的 Referer
    if 'alicdn.com' in domain or 'taobao.com' in domain or 'tmall.com' in domain:
        # 阿里系图片需要淘宝的 Referer
        headers['Referer'] = 'https://www.taobao.com/'
    elif 'findqc.com' in domain:
        headers['Referer'] = 'https://www.findqc.com/'
    elif 'cdn.findqc.com' in domain:
        headers['Referer'] = 'https://www.findqc.com/'
    else:
        # 默认使用配置的 Referer
        pass
    
    return headers


def compress_image(filepath: Path, max_size: int = None, quality: int = 80, convert_to_webp: bool = False, keep_original: bool = False) -> bool:
    """
    压缩图片以节省 token
    如果图片尺寸小于 max_size，则不进行压缩处理
    
    Args:
        filepath: 图片文件路径
        max_size: 最大尺寸（像素），保持宽高比。如果图片宽高都小于等于此值，则跳过压缩
        quality: JPEG 质量（1-100）
        convert_to_webp: 是否转换为 WebP 格式
        keep_original: 是否保留原始文件
        
    Returns:
        是否压缩成功（如果跳过压缩返回 True）
    """
    try:
        # 打开图片检查尺寸
        with Image.open(filepath) as img:
            width, height = img.size
            
            # 如果设置了 max_size，且图片宽高都小于等于 max_size，跳过压缩
            if max_size and width <= max_size and height <= max_size:
                # 图片已经足够小，不需要压缩
                return True
            
            # 如果需要保留原图，先复制到 original 目录
            if keep_original:
                original_dir = filepath.parent.parent / 'original' / filepath.parent.name
                original_dir.mkdir(parents=True, exist_ok=True)
                original_path = original_dir / filepath.name
                import shutil
                shutil.copy2(filepath, original_path)
            
            original_size = img.size
            original_mode = img.mode
            
            # 转换为 RGB（如果是 RGBA 或其他格式）
            if img.mode in ('RGBA', 'LA', 'P'):
                # 创建白色背景
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 调整尺寸（只有大于 max_size 的图片才需要调整）
            if max_size:
                width, height = img.size
                if width > max_size or height > max_size:
                    # 计算新尺寸，保持宽高比
                    if width > height:
                        new_width = max_size
                        new_height = int(height * max_size / width)
                    else:
                        new_height = max_size
                        new_width = int(width * max_size / height)
                    
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 保存压缩后的图片
            if convert_to_webp:
                output_path = filepath.with_suffix('.webp')
                img.save(output_path, 'WEBP', quality=quality, method=6)
                # 删除原文件
                if output_path != filepath:
                    filepath.unlink()
                    # 更新文件路径引用（如果需要）
                    return True
            else:
                # 保存为 JPEG（覆盖原文件）
                img.save(filepath, 'JPEG', quality=quality, optimize=True)
            
        return True
    except Exception as e:
        # 压缩失败不影响下载，只记录错误
        return False


def download_image(url: str, filepath: Path, retry_times: int = None, silent: bool = False, session: requests.Session = None) -> bool:
    """
    下载单张图片
    
    Args:
        url: 图片 URL
        filepath: 保存路径
        retry_times: 重试次数
        silent: 是否静默模式（不打印错误信息）
        
    Returns:
        是否下载成功
    """
    if retry_times is None:
        retry_times = config.RETRY_TIMES
    
    # 如果文件已存在，跳过下载
    if filepath.exists():
        return True
    
    # 根据 URL 获取合适的请求头
    headers = get_headers_for_url(url)
    
    # 使用 Session 复用连接（提高速度）
    if session is None:
        session = requests.Session()
    
    for attempt in range(retry_times + 1):
        try:
            response = session.get(
                url,
                headers=headers,
                timeout=config.DOWNLOAD_TIMEOUT,
                stream=True,
                allow_redirects=True,
                verify=False  # 跳过SSL验证，提高速度（仅用于图片下载）
            )
            
            if response.status_code == 200:
                # 确保目录存在
                filepath.parent.mkdir(parents=True, exist_ok=True)
                
                # 写入文件（使用更大的块大小提高速度）
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=config.CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                
                # 如果启用压缩，压缩图片
                if config.ENABLE_IMAGE_COMPRESSION:
                    # 获取当前压缩模式的配置
                    mode_config = config.COMPRESSION_MODES.get(config.COMPRESSION_MODE, config.COMPRESSION_MODES['balanced'])
                    compress_image(
                        filepath,
                        max_size=mode_config['max_size'],
                        quality=mode_config['quality'],
                        convert_to_webp=config.CONVERT_TO_WEBP,
                        keep_original=config.KEEP_ORIGINAL
                    )
                
                return True
            elif response.status_code == 403:
                # 403 错误，尝试不同的 Referer
                if attempt < retry_times:
                    # 尝试使用淘宝的 Referer
                    if 'alicdn.com' in url.lower():
                        headers['Referer'] = 'https://item.taobao.com/'
                    # 减少重试延迟
                    time.sleep(config.RETRY_DELAY)
                    continue
                else:
                    if not silent:
                        print(f"  下载失败 (403): {url[:80]}...")
                    return False
            else:
                if attempt < retry_times:
                    # 减少重试延迟
                    time.sleep(config.RETRY_DELAY)
                    continue
                else:
                    if not silent:
                        print(f"  下载失败 ({response.status_code}): {url[:80]}...")
                    return False
                    
        except requests.exceptions.Timeout:
            if attempt < retry_times:
                # 减少重试延迟
                time.sleep(config.RETRY_DELAY)
                continue
            else:
                if not silent:
                    print(f"  下载超时: {url[:80]}...")
                return False
        except Exception as e:
            if attempt < retry_times:
                # 减少重试延迟
                time.sleep(config.RETRY_DELAY)
                continue
            else:
                if not silent:
                    print(f"  下载出错: {url[:80]}... - {str(e)[:50]}")
                return False
    
    return False


def download_product_images(item: Dict[str, Any], images_dir: Path, silent: bool = True, session: requests.Session = None) -> Dict[str, Any]:
    """
    下载单个商品的所有图片
    
    Args:
        item: 商品数据字典
        images_dir: 图片保存目录
        silent: 是否静默模式（不打印单个图片的错误）
        
    Returns:
        图片映射字典
    """
    global _download_stats
    
    item_id = item.get('itemId', '')
    if not item_id:
        return {}
    
    mapping = {
        'itemId': item_id,
        'imageList': [],
        'imageUrlList': []
    }
    
    image_list = []
    image_url_list = []
    
    # 下载主图
    main_images = item.get('mainImages', [])
    for idx, url in enumerate(main_images):
        if not url:
            continue
        
        filename = generate_image_filename(url, item_id, 'main', idx)
        filepath = images_dir / 'main' / filename
        local_path = str(filepath.relative_to(images_dir))
        
        # 检查文件是否已存在
        if filepath.exists():
            _download_stats['skipped'] += 1
            image_list.append(local_path)
            image_url_list.append(url)
        elif download_image(url, filepath, silent=silent, session=session):
            _download_stats['success'] += 1
            image_list.append(local_path)
            image_url_list.append(url)
        else:
            _download_stats['failed'] += 1
            if 'alicdn.com' in url.lower():
                _download_stats['403_errors'] += 1
    
    # 下载 SKU 图
    sku_images = item.get('skuImages', [])
    for idx, url in enumerate(sku_images):
        if not url:
            continue
        
        filename = generate_image_filename(url, item_id, 'sku', idx)
        filepath = images_dir / 'sku' / filename
        local_path = str(filepath.relative_to(images_dir))
        
        if filepath.exists():
            _download_stats['skipped'] += 1
            image_list.append(local_path)
            image_url_list.append(url)
        elif download_image(url, filepath, silent=silent, session=session):
            _download_stats['success'] += 1
            image_list.append(local_path)
            image_url_list.append(url)
        else:
            _download_stats['failed'] += 1
            if 'alicdn.com' in url.lower():
                _download_stats['403_errors'] += 1
    
    # 下载 QC 图
    qc_images = item.get('qcImages', [])
    for idx, url in enumerate(qc_images):
        if not url:
            continue
        
        filename = generate_image_filename(url, item_id, 'qc', idx)
        filepath = images_dir / 'qc' / filename
        local_path = str(filepath.relative_to(images_dir))
        
        if filepath.exists():
            _download_stats['skipped'] += 1
            image_list.append(local_path)
            image_url_list.append(url)
        elif download_image(url, filepath, silent=silent, session=session):
            _download_stats['success'] += 1
            image_list.append(local_path)
            image_url_list.append(url)
        else:
            _download_stats['failed'] += 1
            if 'alicdn.com' in url.lower():
                _download_stats['403_errors'] += 1
    
    mapping['imageList'] = image_list
    mapping['imageUrlList'] = image_url_list
    return mapping


def load_existing_mapping(mapping_file: Path) -> Dict[str, Dict[str, Any]]:
    """
    加载已存在的映射文件，用于断点续传
    支持新旧两种格式：
    - 新格式: {"itemId": "...", "imageList": [...], "imageUrlList": [...]}
    - 旧格式: {"itemId": "...", "imageList": [...]} (没有 imageUrlList)
    - 更旧格式: {"itemId": "...", "mainImages": [...], "skuImages": [...], "qcImages": [...]}
    
    Args:
        mapping_file: 映射文件路径
        
    Returns:
        以 itemId 为 key 的字典
    """
    if not mapping_file.exists():
        return {}
    
    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            mappings = json.load(f)
        
        # 转换为以 itemId 为 key 的字典
        mapping_dict = {}
        for mapping in mappings:
            item_id = mapping.get('itemId')
            if not item_id:
                continue
            
            # 如果是旧格式，转换为新格式
            if 'imageList' not in mapping:
                # 旧格式：合并 mainImages, skuImages, qcImages 到 imageList
                image_list = []
                for img_type in ['mainImages', 'skuImages', 'qcImages']:
                    for img in mapping.get(img_type, []):
                        if isinstance(img, dict):
                            local_path = img.get('localPath', '')
                        else:
                            local_path = str(img)
                        if local_path:
                            image_list.append(local_path)
                mapping = {
                    'itemId': item_id,
                    'imageList': image_list
                }
            
            # 如果没有 imageUrlList，添加空列表（兼容旧格式）
            if 'imageUrlList' not in mapping:
                mapping['imageUrlList'] = []
            
            mapping_dict[item_id] = mapping
        
        return mapping_dict
    except Exception as e:
        print(f"警告: 加载已有映射文件失败: {e}")
        return {}


def save_mapping_file(mapping_file: Path, mappings: List[Dict[str, Any]]):
    """
    保存映射文件（线程安全）
    
    Args:
        mapping_file: 映射文件路径
        mappings: 映射列表
    """
    with _save_lock:
        try:
            # 先保存到临时文件，然后重命名（原子操作）
            temp_file = mapping_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, ensure_ascii=False, indent=2)
            
            # 原子替换
            temp_file.replace(mapping_file)
        except Exception as e:
            print(f"保存映射文件失败: {e}")


def save_pending_tasks(pending_file: Path, items: List[Dict[str, Any]]):
    """
    保存未完成的任务列表（用于中断恢复）
    
    Args:
        pending_file: 未完成任务文件路径
        items: 未完成的任务列表
    """
    try:
        with open(pending_file, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存未完成任务失败: {e}")


def load_pending_tasks(pending_file: Path) -> List[Dict[str, Any]]:
    """
    加载未完成的任务列表（用于中断恢复）
    
    Args:
        pending_file: 未完成任务文件路径
        
    Returns:
        未完成的任务列表
    """
    if not pending_file.exists():
        return []
    
    try:
        with open(pending_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载未完成任务失败: {e}")
        return []


# 全局变量用于信号处理
_global_image_mappings = None
_global_items_to_process = None

def signal_handler(signum, frame):
    """
    信号处理函数（处理 Ctrl+C 等中断信号）
    
    Args:
        signum: 信号编号
        frame: 当前堆栈帧
    
    注意：信号处理器应该尽可能快地执行，不做耗时操作。
    所有保存和清理工作都在主循环中完成。
    """
    global _shutdown_flag, _shutdown_count
    
    with _shutdown_lock:
        _shutdown_count += 1
    
    # 设置关闭标志（让主循环知道需要退出）
    _shutdown_flag.set()
    
    if _shutdown_count == 1:
        # 第一次按 Ctrl+C，提示用户正在退出
        print(f"\n\n{'='*60}")
        print("收到中断信号，正在安全退出...")
        print("请稍候，正在保存进度...")
        print("（再次按 Ctrl+C 将强制退出）")
        print(f"{'='*60}\n")
    elif _shutdown_count >= 2:
        # 第二次按 Ctrl+C，强制退出
        print("\n\n强制退出...")
        sys.exit(1)


def main():
    """
    主函数
    """
    print("=" * 60)
    print("图片下载程序")
    print("=" * 60)
    
    # 1. 检查输入文件
    input_file = config.INPUT_DATA_FILE
    if not input_file.exists():
        print(f"错误: 输入文件 {input_file} 不存在")
        return
    
    # 2. 创建图片保存目录
    images_dir = config.IMAGES_DIR
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建子目录
    (images_dir / 'main').mkdir(exist_ok=True)
    (images_dir / 'sku').mkdir(exist_ok=True)
    (images_dir / 'qc').mkdir(exist_ok=True)
    
    print(f"图片保存目录: {images_dir}")
    
    # 3. 读取数据文件
    print(f"\n读取数据文件: {input_file}")
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"错误: 读取数据文件失败: {e}")
        return
    
    print(f"找到 {len(data)} 个商品")
    
    # 4. 统计需要下载的图片数量
    total_images = 0
    for item in data:
        total_images += len(item.get('mainImages', []))
        total_images += len(item.get('skuImages', []))
        total_images += len(item.get('qcImages', []))
    
    print(f"需要下载的图片总数: {total_images}")
    
    # 4.5. 加载已有映射文件（断点续传）
    mapping_file = config.IMAGE_MAPPING_FILE
    existing_mappings = load_existing_mapping(mapping_file)
    if existing_mappings:
        print(f"发现已有映射文件，已加载 {len(existing_mappings)} 个商品的映射（断点续传）")
        # 统计已下载的图片数量
        existing_images = sum(
            len(m.get('imageList', []))
            for m in existing_mappings.values()
        )
        print(f"  已有图片映射: {existing_images} 张")
    
    # 过滤出需要处理的商品（断点续传：跳过已有映射的商品）
    items_to_process = []
    skipped_items = 0
    for item in data:
        item_id = item.get('itemId', '')
        if item_id and item_id in existing_mappings:
            # 检查所有图片是否都已下载
            existing = existing_mappings[item_id]
            existing_paths = set(existing.get('imageList', []))
            
            # 计算应该有的图片路径
            expected_paths = set()
            for idx, url in enumerate(item.get('mainImages', [])):
                if url:
                    filename = generate_image_filename(url, item_id, 'main', idx)
                    expected_paths.add(f"main/{filename}")
            
            for idx, url in enumerate(item.get('skuImages', [])):
                if url:
                    filename = generate_image_filename(url, item_id, 'sku', idx)
                    expected_paths.add(f"sku/{filename}")
            
            for idx, url in enumerate(item.get('qcImages', [])):
                if url:
                    filename = generate_image_filename(url, item_id, 'qc', idx)
                    expected_paths.add(f"qc/{filename}")
            
            # 如果所有图片都已映射，跳过
            if expected_paths.issubset(existing_paths):
                skipped_items += 1
                continue
        
        items_to_process.append(item)
    
    if skipped_items > 0:
        print(f"跳过已完整处理的商品: {skipped_items} 个")
    print(f"需要处理的商品: {len(items_to_process)} 个")
    
    # 5. 下载图片
    print("\n开始下载图片...")
    print(f"并发数: {config.MAX_WORKERS}")
    print(f"超时时间: {config.DOWNLOAD_TIMEOUT} 秒")
    print(f"重试次数: {config.RETRY_TIMES}")
    print(f"批量保存间隔: 每 {config.MAPPING_SAVE_INTERVAL} 个商品保存一次")
    
    # 显示压缩配置
    if config.ENABLE_IMAGE_COMPRESSION:
        mode_config = config.COMPRESSION_MODES.get(config.COMPRESSION_MODE, config.COMPRESSION_MODES['balanced'])
        print(f"\n图片压缩配置:")
        print(f"  模式: {config.COMPRESSION_MODE} - {mode_config['description']}")
        print(f"  最大尺寸: {mode_config['max_size']}px")
        print(f"  JPEG 质量: {mode_config['quality']}%")
        print(f"  转换为 WebP: {'是' if config.CONVERT_TO_WEBP else '否'}")
        print(f"  保留原图: {'是' if config.KEEP_ORIGINAL else '否'}")
    else:
        print(f"\n图片压缩: 已禁用")
    
    print("-" * 60)
    
    start_time = time.time()
    image_mappings = list(existing_mappings.values()) if existing_mappings else []  # 从已有映射开始
    failed_count = 0
    
    # 重置统计
    global _download_stats, _shutdown_flag, _pending_items, _global_image_mappings, _global_items_to_process
    _download_stats = {'success': 0, 'failed': 0, 'skipped': 0, '403_errors': 0}
    _shutdown_flag.clear()
    _pending_items = []
    _global_image_mappings = image_mappings  # 用于信号处理
    _global_items_to_process = items_to_process  # 用于信号处理
    
    # 加载未完成的任务（如果有）
    pending_tasks = load_pending_tasks(config.PENDING_TASKS_FILE)
    if pending_tasks:
        print(f"\n发现未完成任务: {len(pending_tasks)} 个商品")
        print(f"  将优先处理这些任务")
        # 将未完成任务添加到处理列表的前面
        items_to_process = pending_tasks + items_to_process
        # 删除待办文件（处理完后会重新生成或删除）
        config.PENDING_TASKS_FILE.unlink(missing_ok=True)
    
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
    
    # 创建 Session 池（每个线程一个 Session，复用连接，提高速度）
    session_pool = {}
    session_lock = threading.Lock()
    
    def get_session():
        thread_id = threading.current_thread().ident
        with session_lock:
            if thread_id not in session_pool:
                # 优化 Session 配置，提高下载速度
                session = requests.Session()
                # 使用连接池，提高复用效率
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=10,  # 连接池大小
                    pool_maxsize=20,  # 每个主机的最大连接数
                    max_retries=0  # 禁用自动重试，我们自己处理
                )
                session.mount('http://', adapter)
                session.mount('https://', adapter)
                session_pool[thread_id] = session
            return session_pool[thread_id]
    
    try:
        with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
            # 只提交需要处理的任务
            future_to_item = {
                executor.submit(download_product_images, item, images_dir, silent=True, session=get_session()): item
                for item in items_to_process
            }
            
            # 收集结果
            last_save_count = len(image_mappings)
            processed_count = 0
            completed_items = set()  # 已完成的商品ID集合
            
            # 使用超时轮询方式，避免 future.result() 长时间阻塞
            remaining_futures = set(future_to_item.keys())
            
            while remaining_futures:
                # 检查是否收到中断信号
                if _shutdown_flag.is_set():
                    print("\n收到中断信号，停止处理新任务...")
                    # 取消所有未完成的任务
                    for future in remaining_futures:
                        future.cancel()
                    break
                
                # 检查已完成的任务（使用超时，避免阻塞）
                done_futures = {f for f in remaining_futures if f.done()}
                
                if done_futures:
                    # 处理已完成的任务
                    for future in done_futures:
                        remaining_futures.remove(future)
                        item = future_to_item[future]
                        item_id = item.get('itemId', 'unknown')
                        
                        try:
                            # 获取结果（已经完成，不会阻塞）
                            mapping = future.result(timeout=0.1)
                            if mapping:
                                processed_count += 1
                                completed_items.add(item_id)
                                
                                # 检查是否已存在（合并映射）
                                item_id = mapping.get('itemId')
                                with _mapping_lock:
                                    if item_id in existing_mappings:
                                        # 合并已有映射和新增映射
                                        existing = existing_mappings[item_id]
                                        existing_paths = existing.get('imageList', [])
                                        existing_urls = existing.get('imageUrlList', [])
                                        new_paths = mapping.get('imageList', [])
                                        new_urls = mapping.get('imageUrlList', [])
                                        
                                        # 创建路径到URL的映射
                                        path_to_url = {}
                                        for i, path in enumerate(existing_paths):
                                            if i < len(existing_urls):
                                                path_to_url[path] = existing_urls[i]
                                        for i, path in enumerate(new_paths):
                                            if i < len(new_urls):
                                                path_to_url[path] = new_urls[i]
                                        
                                        # 合并去重路径
                                        merged_paths = list(set(existing_paths) | set(new_paths))
                                        # 保持顺序：main -> sku -> qc
                                        merged_paths.sort(key=lambda x: (
                                            0 if x.startswith('main/') else (1 if x.startswith('sku/') else 2),
                                            x
                                        ))
                                        
                                        # 根据路径顺序生成对应的URL列表
                                        merged_urls = [path_to_url.get(path, '') for path in merged_paths]
                                        
                                        mapping = {
                                            'itemId': item_id,
                                            'imageList': merged_paths,
                                            'imageUrlList': merged_urls
                                        }
                                        # 更新 image_mappings 中的对应项
                                        for i, m in enumerate(image_mappings):
                                            if m.get('itemId') == item_id:
                                                image_mappings[i] = mapping
                                                break
                                        existing_mappings[item_id] = mapping
                                    else:
                                        # 新商品，添加到映射
                                        image_mappings.append(mapping)
                                        if item_id:
                                            existing_mappings[item_id] = mapping
                                
                                # 统计下载的图片数量
                                image_list = mapping.get('imageList', [])
                                main_count = sum(1 for p in image_list if p.startswith('main/'))
                                sku_count = sum(1 for p in image_list if p.startswith('sku/'))
                                qc_count = sum(1 for p in image_list if p.startswith('qc/'))
                                total_count = len(image_list)
                                
                                # 每处理 100 个商品或每 50 个商品显示一次进度
                                if processed_count % 100 == 0 or (processed_count % 50 == 0 and total_count > 0):
                                    print(f"进度: {processed_count}/{len(items_to_process)} - 商品 {item_id}: 主图{main_count} 张, SKU图{sku_count} 张, QC图{qc_count} 张 (共{total_count}张)")
                                
                                # 批量保存映射文件
                                current_count = len(image_mappings)
                                if current_count - last_save_count >= config.MAPPING_SAVE_INTERVAL:
                                    with _mapping_lock:
                                        save_mapping_file(mapping_file, image_mappings.copy())
                                        _global_image_mappings = image_mappings  # 更新全局引用
                                    last_save_count = current_count
                                    print(f"  ✓ 已保存映射文件（{current_count} 个商品）")
                        except Exception as e:
                            failed_count += 1
                            print(f"处理商品 {item_id} 时出错: {str(e)}")
                else:
                    # 如果没有完成的任务，短暂休眠，避免CPU占用过高
                    time.sleep(0.1)
            
            # 如果收到中断信号，保存未完成的任务
            if _shutdown_flag.is_set():
                print("\n" + "=" * 60)
                print("正在保存当前进度...")
                print("=" * 60)
                
                # 等待正在执行的任务完成（最多等待每个任务1秒）
                if remaining_futures:
                    print("等待当前执行的任务完成...")
                    for future in list(remaining_futures):
                        try:
                            # 等待最多1秒
                            mapping = future.result(timeout=1.0)
                            remaining_futures.remove(future)
                            item = future_to_item[future]
                            item_id = item.get('itemId', 'unknown')
                            if mapping:
                                completed_items.add(item_id)
                                # 处理映射数据
                                with _mapping_lock:
                                    item_id = mapping.get('itemId')
                                    if item_id and item_id not in existing_mappings:
                                        image_mappings.append(mapping)
                                        existing_mappings[item_id] = mapping
                        except (TimeoutError, CancelledError):
                            # 任务超时或已取消，跳过
                            pass
                        except Exception as e:
                            print(f"处理商品时出错: {str(e)}")
                
                # 找出未完成的任务
                with _pending_items_lock:
                    _pending_items = [
                        item for item in items_to_process
                        if item.get('itemId') not in completed_items
                    ]
                    if _pending_items:
                        save_pending_tasks(config.PENDING_TASKS_FILE, _pending_items)
                        print(f"✓ 未完成任务已保存: {len(_pending_items)} 个商品")
                        print(f"  文件位置: {config.PENDING_TASKS_FILE}")
                        print(f"  下次运行时会自动恢复这些任务")
                    else:
                        # 如果没有未完成任务，删除待办文件
                        if config.PENDING_TASKS_FILE.exists():
                            config.PENDING_TASKS_FILE.unlink()
                
                # 保存当前映射
                with _mapping_lock:
                    save_mapping_file(mapping_file, image_mappings.copy())
                    _global_image_mappings = image_mappings  # 更新全局引用
                    print(f"✓ 映射文件已保存: {len(image_mappings)} 个商品")
                
                print("\n✓ 数据已安全保存，程序退出")
                print("=" * 60 + "\n")
                return
    
    except KeyboardInterrupt:
        # 处理键盘中断（备用方案）
        # 设置中断标志，让上面的逻辑处理保存和退出
        _shutdown_flag.set()
        signal_handler(signal.SIGINT, None)
        # 如果信号处理器没有退出，则继续执行保存逻辑
        if not _shutdown_flag.is_set():
            return
    
    elapsed_time = time.time() - start_time
    
    # 6. 最终保存映射文件
    print("\n" + "=" * 60)
    print("保存最终映射文件...")
    print("=" * 60)
    
    with _mapping_lock:
        save_mapping_file(mapping_file, image_mappings)
    
    print(f"映射文件已保存: {mapping_file} (共 {len(image_mappings)} 个商品)")
    
    # 如果所有任务都完成了，删除待办文件
    if config.PENDING_TASKS_FILE.exists():
        config.PENDING_TASKS_FILE.unlink()
        print(f"✓ 所有任务已完成，已删除待办文件")
    
    # 7. 打印统计信息
    print("\n" + "=" * 60)
    print("下载完成！")
    print("=" * 60)
    print(f"总商品数: {len(data)}")
    print(f"已处理商品: {len(image_mappings)} 个（包含断点续传）")
    print(f"本次处理: {processed_count} 个")
    print(f"处理失败: {failed_count} 个商品")
    print(f"总耗时: {elapsed_time:.2f} 秒")
    
    # 下载统计
    total_downloaded = _download_stats['success'] + _download_stats['skipped']
    if total_downloaded > 0:
        print(f"\n下载统计:")
        print(f"  下载成功: {_download_stats['success']} 张")
        print(f"  跳过（已存在）: {_download_stats['skipped']} 张")
        print(f"  下载失败: {_download_stats['failed']} 张")
        if _download_stats['403_errors'] > 0:
            print(f"  其中 403 错误: {_download_stats['403_errors']} 张（可能需要特殊处理）")
        print(f"  平均速度: {total_downloaded / elapsed_time:.2f} 张/秒")
    
    # 统计各类型图片数量
    main_total = 0
    sku_total = 0
    qc_total = 0
    for m in image_mappings:
        image_list = m.get('imageList', [])
        main_total += sum(1 for p in image_list if p.startswith('main/'))
        sku_total += sum(1 for p in image_list if p.startswith('sku/'))
        qc_total += sum(1 for p in image_list if p.startswith('qc/'))
    
    print(f"\n图片类型统计:")
    print(f"  主图: {main_total} 张")
    print(f"  SKU图: {sku_total} 张")
    print(f"  QC图: {qc_total} 张")
    
    if _download_stats['403_errors'] > 0:
        print(f"\n⚠️  注意: 有 {_download_stats['403_errors']} 张图片返回 403 错误")
        print(f"   这些图片可能需要特殊的 Referer 或认证，建议检查 URL 是否有效")
    
    print(f"\n图片保存位置:")
    print(f"  主图: {images_dir / 'main'}")
    print(f"  SKU图: {images_dir / 'sku'}")
    print(f"  QC图: {images_dir / 'qc'}")
    print(f"  映射文件: {mapping_file}")


if __name__ == "__main__":
    main()

