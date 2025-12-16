-- 将 price 字段从 FLOAT 类型迁移到 TEXT 类型
-- 
-- 注意：SQLite 不支持直接修改列类型，需要使用以下步骤：
-- 1. 创建新表（使用新的列类型）
-- 2. 复制数据
-- 3. 删除旧表
-- 4. 重命名新表

-- 由于数据库结构可能包含外键约束，建议直接删除数据库重新创建
-- 或者使用以下 SQL（仅适用于简单情况）：

BEGIN TRANSACTION;

-- 1. 创建新表（price 为 TEXT 类型）
CREATE TABLE t_products_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    findqc_id INTEGER NOT NULL UNIQUE,
    itemId TEXT,
    mallType TEXT,
    categoryId INTEGER,
    price TEXT,  -- 改为 TEXT 类型
    weight REAL,
    image_urls TEXT,  -- JSON 存储
    last_qc_time DATETIME,
    qc_count_30days INTEGER,
    introduce TEXT,
    pic_url TEXT,
    update_task_id INTEGER,
    last_update DATETIME,
    status INTEGER NOT NULL DEFAULT 0
);

-- 2. 复制数据（将 price 转换为字符串）
INSERT INTO t_products_new SELECT 
    id,
    findqc_id,
    itemId,
    mallType,
    categoryId,
    CASE 
        WHEN price IS NULL THEN NULL 
        ELSE CAST(price AS TEXT) 
    END AS price,  -- 转换为 TEXT
    weight,
    image_urls,
    last_qc_time,
    qc_count_30days,
    introduce,
    pic_url,
    update_task_id,
    last_update,
    status
FROM t_products;

-- 3. 删除旧表
DROP TABLE t_products;

-- 4. 重命名新表
ALTER TABLE t_products_new RENAME TO t_products;

-- 5. 重新创建索引（如果需要）
CREATE INDEX idx_item_mall ON t_products(itemId, mallType);

COMMIT;

-- 注意：如果表有外键约束，需要先处理相关表
-- 建议在生产环境执行前先备份数据库

