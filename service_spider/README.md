# service_spider - 爬虫服务

从 FindQC API 爬取商品数据，保存到数据库并发送到消息队列。

## 功能说明

1. **分类遍历**: 遍历所有需要爬取的分类
2. **分页处理**: 按页获取商品列表，直到最后一页（`hasMore=False`）
3. **商品详情获取**: 
   - 调用 `/goods/detail` 接口获取商品基本信息
   - 调用 `/goods/atlas` 接口分页获取商品图集（QC图、视频等）
4. **数据存储**: 
   - 保存商品基本信息到 `t_products` 表
   - 创建任务记录到 `t_tasks_products` 表
5. **消息发送**: 发送商品新增消息到 RabbitMQ，通知 AI 处理管道

## 目录结构

```
service_spider/
├── __init__.py          # 包初始化
├── main.py              # 主程序入口（一次性执行）
├── scheduler.py         # 定时任务入口（使用 APScheduler）
├── spider.py            # 爬虫核心逻辑
├── api_client.py        # FindQC API 客户端封装
├── db_service.py        # 数据库操作服务
├── mq_service.py        # 消息队列服务
└── README.md            # 本文档
```

## 使用说明

### 环境配置

1. 配置环境变量（参考 `.env.example`）：
   - 数据库配置：`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
   - RabbitMQ 配置：`RABBITMQ_HOST`, `RABBITMQ_PORT`, 等
   - FindQC API 配置：`FINDQC_API_BASE_URL`, `FINDQC_API_KEY`（可选）

2. 确保数据库和 RabbitMQ 服务已启动

### 运行

#### 一次性执行

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行爬虫服务（执行一次后退出）
python -m service_spider.main
```

#### 定时任务模式

使用 APScheduler 实现定时执行：

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行定时任务服务（持续运行，按配置的时间执行爬虫任务）
python -m service_spider.scheduler
```

**定时任务配置**（通过环境变量）：

```env
# 调度模式：cron（每天指定时间）或 interval（间隔执行）
SPIDER_SCHEDULE_TYPE=cron

# Cron 模式配置（每天 02:00 执行）
SPIDER_CRON_HOUR=2
SPIDER_CRON_MINUTE=0

# Interval 模式配置（每 24 小时执行一次）
# SPIDER_INTERVAL_HOURS=24
```

**示例**：
- 每天凌晨 2:00 执行：`SPIDER_SCHEDULE_TYPE=cron SPIDER_CRON_HOUR=2 SPIDER_CRON_MINUTE=0`
- 每 12 小时执行一次：`SPIDER_SCHEDULE_TYPE=interval SPIDER_INTERVAL_HOURS=12`

### 配置说明

#### 分类列表配置

当前分类列表在 `spider.py` 的 `get_target_categories()` 方法中硬编码。实际使用时应该：

1. 从配置文件读取
2. 从数据库读取
3. 从命令行参数传入

示例修改：

```python
async def get_target_categories(self) -> List[Dict[str, Any]]:
    # 从配置文件读取
    categories = load_categories_from_config()
    return categories
```

#### 爬虫参数配置

在 `main.py` 中可以调整：

- `page_size`: 每页商品数量（默认 20）
- `delay_between_requests`: 请求之间的延迟（默认 0.5 秒）

## 核心流程

### 1. 主流程

```
开始
  ↓
获取分类列表
  ↓
for 每个分类:
  ↓
  分页获取商品列表 (while True)
    ↓
    for 每个商品:
      ↓
      获取商品详情
      ↓
      获取商品图集（分页）
      ↓
      整理图片结构（QC图、主图、SKU图）
      ↓
      保存到数据库
      ↓
      创建任务记录
      ↓
      发送消息到 RabbitMQ
      ↓
    end
    ↓
    判断是否最后一页
    ↓
    否 → 翻页继续
    ↓
    是 → 下一个分类
  ↓
end
  ↓
完成
```

### 2. 数据流

```
FindQC API
  ↓
商品列表 (getCategoryProducts)
  ↓
商品详情 (get_product_detail)
  ↓
商品图集 (get_product_atlas)
  ↓
数据整理 (prepare_product_data)
  ↓
MySQL (t_products, t_tasks_products)
  ↓
RabbitMQ (product.new 消息)
```

## API 接口说明

### getCategoryProducts

获取分类下的商品列表（分页）

- URL: `/goods/getCategoryProducts`
- 参数: `catalogueId`, `page`, `size`, `currencyType`, `langType`
- 返回: 商品列表 + `hasMore` 标志

### get_product_detail

获取商品详细信息

- URL: `/goods/detail`
- 参数: `itemId`, `mallType`, `currencyType`, `langType`, `notNeedQc`
- 返回: 商品详情（包含主图、SKU图、QC图等）

### get_product_atlas

获取商品图集（QC图、视频）

- URL: `/goods/atlas`
- 参数: `goodsId`, `itemId`, `mallType`, `page`, `size`
- 返回: 图集列表 + `hasMore` 标志

## 消息格式

发送到 RabbitMQ 的消息格式：

```json
{
  "task_id": 2024052001,
  "findqc_id": 12345,
  "product_id": 1001,
  "itemId": "ext_999",
  "mallType": "taobao",
  "action": "product.new",
  "timestamp": "2024-05-20T10:00:00Z"
}
```

## 注意事项

1. **请求频率控制**: 代码中已添加请求延迟（`delay_between_requests`），避免被 API 限流
2. **错误处理**: 单个商品处理失败不会影响整体流程，会记录错误日志并继续
3. **事务管理**: 每个商品的数据库操作都在独立事务中，失败会回滚
4. **消息队列**: 消息发送失败不会影响数据库保存，但会记录错误日志

## 日志

日志输出位置：
- 控制台输出（标准输出）
- 文件：`logs/spider_YYYY-MM-DD.log`（按天轮转，保留30天）

日志级别可通过环境变量 `LOG_LEVEL` 配置（默认 `INFO`）。

## 待优化项

- [ ] 支持并发处理多个分类
- [ ] 支持断点续传（记录已处理的分类/商品）
- [ ] 支持配置化的分类列表
- [ ] 优化图片数据处理性能
- [ ] 添加监控和统计功能

---

**维护者**: MadPrinter  
**最后更新**: 2025-12-16

