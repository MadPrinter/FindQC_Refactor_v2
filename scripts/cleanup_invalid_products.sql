-- 清理不符合条件的商品数据
-- 删除没有 QC 图时间戳或 QC 图时间超过30天的商品

USE findqc_db;

-- 查看将要删除的商品
SELECT 
    id,
    findqc_id,
    itemId,
    last_qc_time,
    CASE 
        WHEN last_qc_time IS NULL THEN '无时间戳'
        WHEN last_qc_time < DATE_SUB(NOW(), INTERVAL 30 DAY) THEN CONCAT('超过30天（', TIMESTAMPDIFF(DAY, last_qc_time, NOW()), '天前）')
        ELSE '符合条件'
    END as reason
FROM t_products
WHERE last_qc_time IS NULL 
    OR last_qc_time < DATE_SUB(NOW(), INTERVAL 30 DAY);

-- 如果要删除，取消下面的注释
-- DELETE FROM t_products
-- WHERE last_qc_time IS NULL 
--     OR last_qc_time < DATE_SUB(NOW(), INTERVAL 30 DAY);

