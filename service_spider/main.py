"""
service_spider 主程序入口

启动爬虫服务。
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared_lib.config import settings
from shared_lib.database import get_database, init_database
from service_spider.api_client import FindQCAPIClient
from service_spider.spider import SpiderService
from service_spider.mq_service import mq_service


async def main():
    """主函数"""
    # 配置日志
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=settings.log_level,
    )
    logger.add(
        "logs/spider_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        level=settings.log_level,
    )
    
    logger.info("=" * 60)
    logger.info("FindQC 爬虫服务启动")
    logger.info("=" * 60)
    
    # 初始化数据库
    try:
        db = init_database(settings.database_url)
        await db.init_db()
        logger.info("数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        sys.exit(1)
    
    # 初始化消息队列（测试时可以跳过）
    try:
        await mq_service.initialize()
        logger.info("消息队列初始化成功")
    except Exception as e:
        logger.warning(f"消息队列初始化失败（将跳过消息发送）: {e}")
        # 消息队列失败不影响爬虫运行
        mq_service._initialized = False  # 标记为未初始化，避免后续调用
    
    # 初始化 API 客户端
    api_client = FindQCAPIClient(
        base_url=settings.findqc_api_base_url,
        api_key=settings.findqc_api_key,
    )
    
    # 创建爬虫服务
    spider_service = SpiderService(
        api_client=api_client,
        page_size=20,  # 每页商品数量
        delay_between_requests=0.5,  # 请求延迟（秒）
    )
    
    try:
        # 生成任务ID（可以根据实际需求调整）
        update_task_id = int(datetime.now().strftime("%Y%m%d%H"))
        logger.info(f"任务批次ID: {update_task_id}")
        
        # 测试模式：只爬取前10个商品
        max_products = settings.max_products
        if max_products is None:
            # 如果配置中没有设置，尝试从环境变量读取（默认10个用于测试）
            import os
            max_products = int(os.getenv("MAX_PRODUCTS", "10"))
        logger.info(f"测试模式：最多爬取 {max_products} 个商品")
        
        # 运行爬虫主流程
        await spider_service.spider_main_process(
            update_task_id=update_task_id,
            max_products=max_products,
        )
        
        logger.info("=" * 60)
        logger.info("爬虫服务执行完成")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止...")
    except Exception as e:
        logger.error(f"爬虫服务执行失败: {e}")
        raise
    finally:
        # 清理资源
        await api_client.close()
        await mq_service.close()
        db = get_database()
        await db.close()
        logger.info("资源清理完成")


if __name__ == "__main__":
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 运行主程序
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
        sys.exit(1)

