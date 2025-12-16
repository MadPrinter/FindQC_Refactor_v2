# 配置文件说明

## 概述

`config.py` 文件包含了 `extract_data.py` 中所有可配置的参数。通过修改配置文件，可以轻松调整程序的行为，而无需修改主程序代码。

## 配置项说明

### 1. 文件路径配置

```python
DB_PATH = Path("findqc_local_data.db")      # 数据库文件路径
OUTPUT_FILE = Path("cleaned_data.json")      # 输出JSON文件路径
```

### 2. 图片数量限制配置

```python
MAX_MAIN_IMAGES = 3    # 主图最多选择数量
MAX_SKU_IMAGES = 3     # SKU图最多选择数量
MAX_QC_IMAGES = 3      # QC图最多选择数量
```

**说明**：这些参数控制每种类型的图片最多提取多少张。可以根据需要调整这些数值。

### 3. 进度显示配置

```python
PROGRESS_INTERVAL = 1000    # 每处理 N 条记录打印一次进度
```

**说明**：控制进度信息的打印频率。如果数据量很大，可以增大这个值以减少输出；如果需要更频繁的进度更新，可以减小这个值。

### 4. 数据库表配置

```python
REQUIRED_TABLES = ['products', 'product_details_full', 'product_media']
PRODUCTS_TABLE = 'products'
PRODUCT_DETAILS_TABLE = 'product_details_full'
PRODUCT_MEDIA_TABLE = 'product_media'
PRODUCT_SKUS_TABLE = 'product_skus'
```

**说明**：如果数据库表名发生变化，可以在这里修改。

### 5. 图片查询配置

```python
# 主图查询条件
MAIN_IMAGE_SOURCE_TYPE = 'main'
MAIN_IMAGE_MEDIA_TYPE = 'image'

# SKU图查询条件
SKU_IMAGE_SOURCE_TYPE = 'sku'
SKU_IMAGE_MEDIA_TYPE = 'image'

# QC图查询条件
QC_IMAGE_SOURCE_TYPES = ['atlas_qc', 'detail_qc']
QC_IMAGE_MEDIA_TYPE = 'image'
```

**说明**：这些参数控制从数据库中查询图片时的筛选条件。如果数据库中的 `source_type` 或 `media_type` 值发生变化，可以在这里修改。

### 6. 数据筛选配置

```python
# 是否启用销售数据筛选（只保留在销售文件中的商品）
ENABLE_SALES_FILTER = True

# 销售数据筛选文件路径
SALES_FILTER_FILE = Path("sales_30days_ns.json")
```

**说明**：
- `ENABLE_SALES_FILTER`: 是否启用筛选功能。设置为 `False` 则不进行筛选，输出所有数据。
- `SALES_FILTER_FILE`: 销售数据文件路径。文件格式应为 JSON 数组，每个元素包含 `itemId` 字段。
  - 例如：`[{"itemId": "123", "sales30": 10}, ...]`
  - 如果文件不存在或为空，程序会给出警告并继续处理（不进行筛选）

**筛选逻辑**：程序会读取销售文件中的所有 `itemId`，只保留 `itemId` 在销售文件中的商品数据。

## 使用示例

### 示例1：增加图片数量

如果需要提取更多的主图和QC图：

```python
MAX_MAIN_IMAGES = 5    # 从3张增加到5张
MAX_QC_IMAGES = 10     # 从3张增加到10张
```

### 示例2：修改输出文件路径

```python
OUTPUT_FILE = Path("output/cleaned_data.json")    # 输出到output目录
```

### 示例3：调整进度显示频率

```python
PROGRESS_INTERVAL = 500    # 每500条记录显示一次进度（更频繁）
```

### 示例4：修改数据库路径

```python
DB_PATH = Path("../findqc_getdata/findqc_local_data.db")    # 使用相对路径
# 或
DB_PATH = Path("/absolute/path/to/findqc_local_data.db")    # 使用绝对路径
```

### 示例5：启用/禁用销售筛选

```python
# 启用筛选（只保留在销售文件中的商品）
ENABLE_SALES_FILTER = True
SALES_FILTER_FILE = Path("sales_30days_ns.json")

# 禁用筛选（输出所有商品）
ENABLE_SALES_FILTER = False

# 使用不同的销售文件
SALES_FILTER_FILE = Path("sales_30days_0s.json")
```

## 注意事项

1. 修改配置后，需要重新运行 `extract_data.py` 才能生效
2. 确保数据库文件路径正确，否则程序会报错
3. 图片数量限制建议不要设置过大，以免影响性能和输出文件大小
4. 如果修改了表名或查询条件，请确保数据库结构匹配

## 配置验证

可以通过以下命令验证配置是否正确：

```bash
python3 -c "import config; print('配置导入成功！')"
```

