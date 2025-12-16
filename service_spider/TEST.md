# service_spider 测试指南

## 测试状态

✅ **API 测试已通过** - FindQC API 可以正常访问

测试结果：
- 成功获取分类商品列表
- 成功获取商品详情（包含主图、QC图、SKU信息）
- 成功获取商品图集

## 快速测试（不依赖数据库）

如果你想先测试 API 是否能正常访问，可以运行：

```bash
python3 test_spider_simple.py
```

这个脚本只测试 API 调用，不需要数据库和 RabbitMQ。

## 完整测试（需要数据库）

如果要测试完整的爬虫功能（包括数据保存），需要：

### 1. 安装依赖

```bash
# 激活虚拟环境（如果有）
source venv/bin/activate

# 安装必要依赖
pip install sqlalchemy aiomysql loguru httpx pydantic-settings
```

### 2. 配置数据库

创建 `.env` 文件（参考 `.env.example`）：

```env
# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=findqc_db

# 日志级别
LOG_LEVEL=INFO

# 测试模式：只爬取10个商品
MAX_PRODUCTS=10
```

### 3. 初始化数据库

需要先创建 MySQL 数据库和表结构。可以：

1. 手动创建数据库：
   ```sql
   CREATE DATABASE findqc_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

2. 运行代码会自动创建表结构（通过 `db.init_db()`）

### 4. 运行测试

```bash
# 设置环境变量（或使用 .env 文件）
export MAX_PRODUCTS=10

# 运行爬虫（测试模式，只爬10个商品）
python3 -m service_spider.main
```

### 5. 查看结果

- 日志输出在控制台和 `logs/spider_YYYY-MM-DD.log`
- 数据库中的 `t_products` 表应该有爬取的商品数据
- `t_tasks_products` 表应该有任务记录

## 测试模式说明

通过环境变量 `MAX_PRODUCTS` 可以控制爬取的商品数量：

- `MAX_PRODUCTS=10` - 只爬取10个商品（测试用）
- 不设置或设置为 0 - 爬取所有商品（生产模式）

## 注意事项

1. **消息队列（RabbitMQ）**: 
   - 如果未配置 RabbitMQ，爬虫仍然可以运行
   - 只是不会发送消息到队列（会有警告日志）
   - 不影响数据保存

2. **请求频率**:
   - 代码中已设置请求延迟（默认 0.5 秒）
   - 如果被限流，可以增加延迟时间

3. **分类ID**:
   - 当前使用分类ID `4113` 进行测试
   - 可以从旧项目的 `goods_data_tree` 目录中找到更多分类ID
   - 修改 `spider.py` 中的 `get_target_categories()` 方法可以更改分类列表

## 故障排除

### 问题1: ModuleNotFoundError

```
ModuleNotFoundError: No module named 'sqlalchemy'
```

**解决**: 安装依赖
```bash
pip install -r requirements.txt
```

### 问题2: 数据库连接失败

```
Can't connect to MySQL server
```

**解决**: 
- 检查 MySQL 服务是否启动
- 检查 `.env` 文件中的数据库配置是否正确
- 确认数据库用户有创建表的权限

### 问题3: API 请求失败

```
HTTPStatusError: 429 Too Many Requests
```

**解决**: 增加请求延迟时间（修改 `main.py` 中的 `delay_between_requests` 参数）

### 问题4: 分类没有商品

如果指定的分类ID没有商品，爬虫会跳过该分类。可以：

1. 查看日志找到有商品的其他分类ID
2. 修改代码中的分类ID列表

---

**维护者**: MadPrinter  
**最后更新**: 2025-12-16

