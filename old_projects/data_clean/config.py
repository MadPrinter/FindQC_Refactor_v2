#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_clean 模块配置文件

功能说明：
集中管理 data_clean 目录下所有 Python 程序的配置参数

包含的配置模块：
1. 文件路径配置：数据库文件、输出文件路径
2. 图片数量限制：主图、SKU图、QC图的最大数量
3. 数据库表配置：表名、字段映射
4. 图片下载配置：并发数、超时、重试等
5. 图片压缩配置：压缩模式、质量设置
6. 重复 ID 分析配置：需要分析的数据文件列表

使用方式：
- 各个程序通过 `import config` 导入配置
- 修改此文件即可调整所有程序的参数，无需修改程序代码
"""

from pathlib import Path

# ==================== 文件路径配置 ====================
# 数据库文件路径
DB_PATH = Path("findqc_local_data.db")

# 输出文件路径
OUTPUT_FILE = Path("cleaned_data.json")

# 重复 ID 分析配置
# 需要分析的数据文件列表
DUPLICATE_ANALYSIS_FILES = [
    {
        "name": "cleaned_data",
        "file": Path("cleaned_data.json"),
        "id_field": "id",  # ID 字段名
        "output": Path("duplicate_ids_cleaned_data.json")
    },
    {
        "name": "sales_30days_30s",
        "file": Path("sales_30days_30s.json"),
        "id_field": "itemId",  # ID 字段名
        "output": Path("duplicate_ids_sales_30days_30s.json")
    }
]


# ==================== 图片数量限制配置cleaned_data.py ====================
# 主图最多选择数量
MAX_MAIN_IMAGES = 3

# SKU图最多选择数量
MAX_SKU_IMAGES = 3

# QC图最多选择数量
MAX_QC_IMAGES = 3


# ==================== 进度显示配置 ====================
# 处理进度打印间隔（每处理 N 条记录打印一次进度）
PROGRESS_INTERVAL = 1000


# ==================== 数据库表配置 ====================
# 必需的表名列表
REQUIRED_TABLES = ['products', 'product_details_full', 'product_media']

# 主表名
PRODUCTS_TABLE = 'products'

# 详情表名
PRODUCT_DETAILS_TABLE = 'product_details_full'

# 媒体表名
PRODUCT_MEDIA_TABLE = 'product_media'

# SKU表名
PRODUCT_SKUS_TABLE = 'product_skus'


# ==================== 图片查询配置 ====================
# 主图查询条件
MAIN_IMAGE_SOURCE_TYPE = 'main'
MAIN_IMAGE_MEDIA_TYPE = 'image'

# SKU图查询条件
SKU_IMAGE_SOURCE_TYPE = 'sku'
SKU_IMAGE_MEDIA_TYPE = 'image'

# QC图查询条件（支持多个 source_type）
QC_IMAGE_SOURCE_TYPES = ['atlas_qc', 'detail_qc']
QC_IMAGE_MEDIA_TYPE = 'image'


# ==================== 输出字段配置 ====================
# 输出JSON中的字段映射
OUTPUT_FIELDS = {
    'id': 'id',
    'mallType': 'mall_type',
    'itemId': 'item_id',
    'toPrice': 'to_price',
    'itemUrl': 'item_url',
    'mainImages': 'mainImages',
    'skuImages': 'skuImages',
    'qcImages': 'qcImages',
}


# ==================== 数据筛选配置 ====================
# 是否启用销售数据筛选（只保留在销售文件中的商品）
ENABLE_SALES_FILTER = True

# 销售数据筛选文件路径（用于筛选 itemId）
# 如果设置为 None 或空字符串，则不进行筛选
# 文件格式应为 JSON 数组，每个元素包含 itemId 字段
SALES_FILTER_FILE = Path("sales.json")


# ==================== 图片下载配置download_images.py ====================
# 输入数据文件路径
INPUT_DATA_FILE = Path("cleaned_data.json")

# 图片保存目录
IMAGES_DIR = Path("downloaded_images")

# 图片映射 JSON 文件路径
IMAGE_MAPPING_FILE = Path("download_mapping.json")

# 未完成任务保存文件路径（用于中断恢复）
PENDING_TASKS_FILE = Path("download_pending_tasks.json")

# 下载配置
MAX_WORKERS = 50  # 并发下载线程数（提高速度，可根据网络调整）
DOWNLOAD_TIMEOUT = 20  # 下载超时时间（秒，减少等待）
RETRY_TIMES = 3  # 失败重试次数（减少重试，加快速度）
RETRY_DELAY = 0.5  # 重试延迟（秒，减少等待）
CHUNK_SIZE = 65536  # 下载块大小（64KB，提高下载速度）

# 批量保存配置
MAPPING_SAVE_INTERVAL = 50  # 每处理 N 个商品保存一次映射文件

# 请求头（用于下载图片）
DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.findqc.com/",
}


# ==================== 图片压缩配置 ====================
# 压缩模式选择: 'ultra_minimal', 'minimal', 'balanced', 'high_quality'
# - 'ultra_minimal': 超极致节省模式（最小 token，质量最低）
#   - 尺寸: 255px, 质量: 70%, 预估节省: ~95% token
#   - 说明: 只压缩大于 255px 的图片，小于等于 255px 的图片直接使用
# - 'minimal': 极致节省模式（最小 token，质量较低）
#   - 尺寸: 512px, 质量: 75%, 预估节省: ~90% token
#   - 说明: 只压缩大于 512px 的图片，小于等于 512px 的图片直接使用
# - 'balanced': 平衡模式（推荐，质量与大小平衡）
#   - 尺寸: 1024px, 质量: 80%, 预估节省: ~80% token
#   - 说明: 只压缩大于 1024px 的图片，小于等于 1024px 的图片直接使用
# - 'high_quality': 高质量模式（较大 token，质量较高）
#   - 尺寸: 1536px, 质量: 85%, 预估节省: ~60% token
#   - 说明: 只压缩大于 1536px 的图片，小于等于 1536px 的图片直接使用
COMPRESSION_MODE = 'high_quality'  # 默认使用平衡模式

# 压缩模式配置字典（内部使用，无需修改）
COMPRESSION_MODES = {
    'ultra_minimal': {
        'max_size': 255,      # 最大尺寸（像素）
        'quality': 70,        # JPEG 质量（1-100）
        'description': '超极致节省模式（最小 token，质量最低）'
    },
    'minimal': {
        'max_size': 512,      # 最大尺寸（像素）
        'quality': 75,        # JPEG 质量（1-100）
        'description': '极致节省模式（最小 token，质量较低）'
    },
    'balanced': {
        'max_size': 1024,     # 最大尺寸（像素）
        'quality': 80,        # JPEG 质量（1-100）
        'description': '平衡模式（推荐，质量与大小平衡）'
    },
    'high_quality': {
        'max_size': 1536,     # 最大尺寸（像素）
        'quality': 90,        # JPEG 质量（1-100）
        'description': '高质量模式（较大 token，质量较高）'
    }
}

# 是否启用图片压缩（节省 token）
# 如果设置为 False，则不进行压缩
ENABLE_IMAGE_COMPRESSION = True

# 是否转换为 WebP 格式（更小的文件大小）
# WebP 通常比 JPEG 小 25-35%，但某些模型可能不支持
# 建议先测试模型是否支持 WebP，再启用
CONVERT_TO_WEBP = False

# 如果启用压缩，是否保留原始文件
# 如果为 True，原图会保存到 original/ 目录
KEEP_ORIGINAL = False

