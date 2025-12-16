-- MySQL 数据库初始化脚本
-- 用于创建 FindQC 项目所需的数据库和用户

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS findqc_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 使用数据库
USE findqc_db;

-- 注意：表结构会通过 SQLAlchemy 自动创建，这里只需要创建数据库即可
-- 如果需要手动创建用户和授权，可以使用以下命令（需要 MySQL root 权限）：
-- CREATE USER IF NOT EXISTS 'findqc_user'@'localhost' IDENTIFIED BY 'your_password';
-- GRANT ALL PRIVILEGES ON findqc_db.* TO 'findqc_user'@'localhost';
-- FLUSH PRIVILEGES;

