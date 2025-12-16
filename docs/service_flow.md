# 服务流程图文档

本文档详细描述 FindQC 商品重构与 AI 聚类系统的完整业务流程，包括各个微服务之间的交互和数据处理流程。

## 一、总体业务流程概览

```mermaid
flowchart TD
    Start([开始]) --> Spider[service_spider<br/>爬虫服务]
    Spider --> |商品数据| DB1[(MySQL<br/>t_products)]
    Spider --> |任务消息| MQ1[RabbitMQ<br/>product.new]
    
    MQ1 --> AIPipe[service_ai_pipe<br/>AI处理管道]
    AIPipe --> |Qwen API| Qwen1[选图 + 初打标签]
    AIPipe --> |Google Lens| GLens[识别相似商品]
    AIPipe --> |Qwen API| Qwen2[综合标签]
    AIPipe --> |AI标签| DB2[(MySQL<br/>t_product_tags)]
    AIPipe --> |任务消息| MQ2[RabbitMQ<br/>product.labeled]
    
    MQ2 --> Cluster[service_cluster<br/>聚类服务]
    Cluster --> |阿里云图搜| Aliyun[图片相似度搜索]
    Cluster --> |聚类结果| DB3[(MySQL<br/>t_cluster<br/>t_cluster_members)]
    
    DB3 --> End([完成])
```

## 二、详细服务流程

### 2.1 爬虫服务流程 (service_spider)

```mermaid
sequenceDiagram
    participant Scheduler as 任务调度器
    participant Spider as service_spider
    participant FindQC as FindQC API
    participant DB as MySQL
    participant MQ as RabbitMQ

    Scheduler->>Spider: 触发爬取任务
    
    Note over Spider: 1. 获取分类列表
    Spider->>FindQC: GET /api/goods/getCategoryProducts<br/>(categoryId, page, size)
    FindQC-->>Spider: 返回商品列表
    
    loop 每个分类的每一页
        Spider->>Spider: 判断是否最后一页<br/>(len(items) < page_size)
        
        alt 不是最后一页
            loop 遍历商品列表
                Spider->>FindQC: GET /api/goods/detail<br/>(itemId, mallType)
                FindQC-->>Spider: 返回商品详情<br/>(基本信息 + 图片URLs)
                
                Spider->>Spider: 整理图片结构<br/>(qc_images, main_images, sku_images)
                
                Spider->>DB: 保存/更新 t_products<br/>(findqc_id, itemId, mallType,<br/>image_urls, update_task_id)
                
                Spider->>DB: 记录 t_tasks_products<br/>(findqc_id, update_task_id, status=0)
                
                Spider->>MQ: 发送消息到 product.new<br/>{findqc_id, product_id, action}
            end
        else 最后一页
            Note over Spider: 该分类爬取完成
        end
    end
    
    Spider->>Scheduler: 任务完成
```

### 2.2 AI 处理管道流程 (service_ai_pipe)

```mermaid
sequenceDiagram
    participant MQ as RabbitMQ
    participant AIPipe as service_ai_pipe
    participant Qwen as Qwen API
    participant GLens as Google Lens API
    participant DB as MySQL
    participant MQ2 as RabbitMQ

    MQ->>AIPipe: 消费消息<br/>(product.new)
    
    Note over AIPipe: 步骤1: Qwen 选图 + 初打标签
    AIPipe->>DB: 查询商品数据<br/>(image_urls)
    DB-->>AIPipe: 返回图片URL列表
    
    AIPipe->>Qwen: 请求分析商品图片<br/>{images: [...], prompt: "选择1-3张正面图并生成标签"}
    Qwen-->>AIPipe: 返回结果<br/>{selected_images: [url1, url2, url3],<br/>initial_tags: {brand, category, ...}}
    
    Note over AIPipe: 步骤2: Google Lens 识别相似商品
    AIPipe->>AIPipe: 选择最佳正面图<br/>(selected_images[0])
    AIPipe->>GLens: 图片搜索请求<br/>(image_url)
    GLens-->>AIPipe: 返回前10条相似商品简介<br/>[{title, description, ...}, ...]
    
    Note over AIPipe: 步骤3: Qwen 综合标签
    AIPipe->>Qwen: 请求综合标签<br/>{initial_tags, google_lens_results,<br/>prompt: "综合生成最终标签"}
    Qwen-->>AIPipe: 返回最终标签<br/>{brand, model, category,<br/>target_audience, season,<br/>environment, keywords,<br/>confidence: 0.95}
    
    Note over AIPipe: 步骤4: 保存结果
    AIPipe->>DB: 更新 t_products<br/>(pic_url=selected_images[0],<br/>introduce=商品简介)
    
    AIPipe->>DB: 保存/更新 t_product_tags<br/>(product_id, brand, model,<br/>category, keywords,<br/>ai_confidence, ...)
    
    AIPipe->>DB: 更新 t_tasks_products<br/>(status=1, 标记AI处理完成)
    
    AIPipe->>MQ2: 发送消息到 product.labeled<br/>{product_id, pic_url, tags, action}
    
    AIPipe->>MQ: 确认消息已处理 (ACK)
```

### 2.3 聚类服务流程 (service_cluster)

```mermaid
sequenceDiagram
    participant MQ as RabbitMQ
    participant Cluster as service_cluster
    participant Aliyun as 阿里云图搜API
    participant DB as MySQL

    MQ->>Cluster: 消费消息<br/>(product.labeled)
    
    Note over Cluster: 1. 查询待聚类商品
    Cluster->>DB: 查询商品数据<br/>(pic_url, itemId, mallType)
    DB-->>Cluster: 返回商品列表
    
    Note over Cluster: 2. 调用图搜API
    loop 遍历每个商品
        Cluster->>Aliyun: 图片相似度搜索<br/>(pic_url)
        Aliyun-->>Cluster: 返回相似商品列表<br/>[{itemId, mallType, score}, ...]
        
        Note over Cluster: 3. 按分值聚类
        Cluster->>Cluster: 过滤相似度 >= 阈值<br/>(score >= 0.85)
        
        alt 找到相似商品
            Cluster->>DB: 查询是否存在cluster<br/>(通过 itemId + mallType)
            
            alt cluster已存在
                Cluster->>DB: 添加到 t_cluster_members<br/>(cluster_code, member_itemId,<br/>member_mallType)
                Cluster->>DB: 更新 t_cluster<br/>(member_count++,<br/>total_sales_count += sales)
            else 创建新cluster
                Cluster->>Cluster: 生成 cluster_code<br/>(mallType_itemId)
                Cluster->>DB: 创建 t_cluster<br/>(cluster_code, center_itemId,<br/>center_mallType, member_count=1)
                Cluster->>DB: 创建 t_cluster_members<br/>(cluster_code, member_itemId,<br/>member_mallType)
            end
        else 无相似商品
            Cluster->>Cluster: 创建新的独立cluster
        end
    end
    
    Cluster->>DB: 更新商品关联<br/>(可选: t_products 关联 cluster_code)
    
    Cluster->>MQ: 确认消息已处理 (ACK)
```

## 三、数据流转详细说明

### 3.1 数据在各阶段的形态变化

```mermaid
flowchart LR
    subgraph "阶段1: 爬虫"
        A1[原始商品数据<br/>findqc_id: 12345<br/>itemId: ext_999<br/>mallType: taobao<br/>image_urls: JSON]
    end
    
    subgraph "阶段2: AI处理"
        A2[增强商品数据<br/>pic_url: selected_image<br/>introduce: 商品简介<br/>tags: {brand, model, ...}]
    end
    
    subgraph "阶段3: 聚类"
        A3[聚类结果<br/>cluster_code: taobao_ext_999<br/>members: [item1, item2, ...]<br/>total_sales: 1500]
    end
    
    A1 -->|Qwen选图<br/>Google Lens<br/>Qwen综合| A2
    A2 -->|阿里云图搜<br/>相似度计算| A3
```

### 3.2 消息队列数据格式

#### product.new 消息格式

```json
{
  "task_id": "2024052001",
  "findqc_id": 12345,
  "product_id": 1001,
  "itemId": "ext_999",
  "mallType": "taobao",
  "action": "product.new",
  "timestamp": "2024-05-20T10:00:00Z"
}
```

#### product.labeled 消息格式

```json
{
  "product_id": 1001,
  "findqc_id": 12345,
  "pic_url": "https://example.com/image.jpg",
  "tags": {
    "brand": "Nike",
    "model": "Air Max 270",
    "category": "运动鞋",
    "target_audience": "年轻人",
    "season": "四季",
    "environment": "运动",
    "keywords": "舒适,透气,时尚",
    "ai_confidence": 0.95
  },
  "action": "product.labeled",
  "timestamp": "2024-05-20T10:05:00Z"
}
```

## 四、错误处理和重试机制

```mermaid
flowchart TD
    Start([服务开始处理]) --> Process[处理业务逻辑]
    Process --> Success{处理成功?}
    
    Success -->|是| Save[保存结果]
    Save --> ACK[发送ACK确认]
    ACK --> End([完成])
    
    Success -->|否| Error{错误类型}
    
    Error -->|临时错误<br/>网络超时| Retry{重试次数 < 3?}
    Retry -->|是| Delay[等待5秒]
    Delay --> Process
    
    Retry -->|否| DeadLetter[发送到死信队列]
    DeadLetter --> Log[记录错误日志]
    Log --> End
    
    Error -->|永久错误<br/>数据格式错误| Log
    Error -->|业务逻辑错误| Manual[标记需要人工处理]
    Manual --> End
```

## 五、服务间的依赖关系

```mermaid
graph TB
    subgraph "外部依赖"
        Ext1[FindQC API]
        Ext2[Qwen API]
        Ext3[Google Lens API]
        Ext4[阿里云图搜API]
    end
    
    subgraph "微服务"
        S1[service_spider]
        S2[service_ai_pipe]
        S3[service_cluster]
    end
    
    subgraph "基础设施"
        DB[(MySQL)]
        MQ[RabbitMQ]
    end
    
    S1 --> Ext1
    S1 --> DB
    S1 --> MQ
    
    S2 --> MQ
    S2 --> Ext2
    S2 --> Ext3
    S2 --> DB
    
    S3 --> MQ
    S3 --> Ext4
    S3 --> DB
    
    MQ -.->|消息传递| S2
    MQ -.->|消息传递| S3
```

## 六、关键业务节点说明

### 6.1 爬虫服务关键节点

| 节点 | 说明 | 输出 |
|------|------|------|
| 分类遍历 | 遍历所有需要爬取的分类ID | 分类ID列表 |
| 分页处理 | 按页获取商品列表，直到 `hasMore=False` | 商品ID列表 |
| 商品详情获取 | 获取每个商品的详细信息 | 商品详情JSON |
| 数据入库 | 保存商品基本信息到 t_products | 数据库记录 |
| 任务创建 | 创建 AI 处理任务记录 | t_tasks_products 记录 |

### 6.2 AI 处理管道关键节点

| 节点 | 说明 | 输入 | 输出 |
|------|------|------|------|
| 图片选择 | Qwen 选择1-3张正面图 | 所有商品图片URLs | 选中的图片URLs |
| 初打标签 | Qwen 生成初始标签 | 选中图片 | 初始标签对象 |
| 相似商品识别 | Google Lens 识别相似商品 | 最佳正面图 | 前10条相似商品简介 |
| 标签综合 | Qwen 综合生成最终标签 | 初始标签 + Google Lens结果 | 最终标签对象 |
| 数据更新 | 更新商品表和标签表 | 标签数据 | 数据库记录 |

### 6.3 聚类服务关键节点

| 节点 | 说明 | 输入 | 输出 |
|------|------|------|------|
| 图片搜索 | 调用阿里云图搜API | 商品正面图URL | 相似商品列表（带分值） |
| 分值过滤 | 过滤相似度阈值以下的商品 | 相似商品列表 | 符合条件的相似商品 |
| 聚类判断 | 判断是否属于已有cluster | 相似商品信息 | cluster_code |
| 聚类创建/更新 | 创建新cluster或添加到现有cluster | 商品信息 | cluster和members记录 |
| 统计更新 | 更新cluster的统计数据 | 成员信息 | 更新的统计字段 |

## 七、性能优化建议

### 7.1 并发处理

```mermaid
flowchart LR
    subgraph "service_spider"
        S1[主线程: 调度]
        S2[线程池: 商品详情获取]
        S3[线程池: 数据库写入]
    end
    
    subgraph "service_ai_pipe"
        A1[消息消费者: 多进程]
        A2[异步API调用: asyncio]
    end
    
    subgraph "service_cluster"
        C1[消息消费者: 多进程]
        C2[批量图搜: 并发请求]
    end
    
    S1 --> S2
    S2 --> S3
    A1 --> A2
    C1 --> C2
```

### 7.2 批量处理优化

- **爬虫服务**: 批量插入数据库，减少数据库连接次数
- **AI 处理**: 批量调用 Qwen API（如果支持）
- **聚类服务**: 批量查询相似商品，减少API调用次数

## 八、监控和日志

### 8.1 关键指标监控

- **爬虫服务**: 爬取速度、成功率、错误率
- **AI 处理**: API调用延迟、标签生成成功率、处理队列长度
- **聚类服务**: 图搜API延迟、聚类准确率、cluster数量

### 8.2 日志记录点

```mermaid
flowchart TD
    Start([服务启动]) --> Log1[记录启动日志]
    Log1 --> Process[业务处理]
    
    Process --> Log2[记录API调用]
    Process --> Log3[记录数据库操作]
    Process --> Log4[记录消息队列操作]
    
    Process --> Error{发生错误?}
    Error -->|是| Log5[记录错误日志<br/>包含堆栈信息]
    Error -->|否| Log6[记录成功日志]
    
    Log5 --> End
    Log6 --> End([服务停止])
```

---

**文档版本**: v1.0  
**最后更新**: 2025-12-16  
**维护者**: MadPrinter

