"""
service_spider 定时任务入口

使用 APScheduler 实现定时执行爬虫任务。
"""

import asyncio
import sys
from pathlib import Path
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from service_spider.main import main as run_spider_task


async def run_spider():
    """
    包装爬虫任务，确保异常不会影响调度器
    
    这个函数会捕获所有异常（包括 SystemExit），确保即使任务失败，调度器也能继续运行。
    """
    try:
        await run_spider_task()
    except SystemExit:
        # 捕获 sys.exit() 调用，但不退出调度器
        logger.warning("爬虫任务调用了 sys.exit()，但不会退出调度器")
    except KeyboardInterrupt:
        # 捕获键盘中断，但不退出调度器（调度器会继续运行）
        logger.warning("爬虫任务收到中断信号，但不会退出调度器")
    except Exception as e:
        logger.error(f"爬虫任务执行失败: {e}", exc_info=True)
        # 不重新抛出异常，让调度器继续运行


def get_scheduler_config():
    """
    获取调度器配置
    
    可以通过环境变量配置：
    - SPIDER_SCHEDULE_TYPE: cron 或 interval（默认 cron）
    - SPIDER_CRON_HOUR: cron 模式的小时（默认 2）
    - SPIDER_CRON_MINUTE: cron 模式的分钟（默认 0）
    - SPIDER_INTERVAL_HOURS: interval 模式的间隔小时数（默认 24）
    """
    import os
    
    schedule_type = os.getenv("SPIDER_SCHEDULE_TYPE", "cron").lower()
    
    if schedule_type == "interval":
        # 间隔模式：每 N 小时执行一次
        interval_hours = int(os.getenv("SPIDER_INTERVAL_HOURS", "24"))
        trigger = IntervalTrigger(hours=interval_hours)
        logger.info(f"使用间隔模式：每 {interval_hours} 小时执行一次")
    else:
        # Cron 模式：每天指定时间执行
        hour = int(os.getenv("SPIDER_CRON_HOUR", "2"))
        minute = int(os.getenv("SPIDER_CRON_MINUTE", "0"))
        trigger = CronTrigger(hour=hour, minute=minute)
        logger.info(f"使用 Cron 模式：每天 {hour:02d}:{minute:02d} 执行")
    
    return trigger


async def main():
    """主函数"""
    # 配置日志
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO",
    )
    logger.add(
        "logs/scheduler_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        level="INFO",
    )
    
    logger.info("=" * 60)
    logger.info("FindQC 爬虫定时任务服务启动")
    logger.info("=" * 60)
    
    # 创建调度器
    scheduler = AsyncIOScheduler()
    
    # 配置触发器
    trigger = get_scheduler_config()
    
    # 添加定时任务
    scheduler.add_job(
        run_spider,
        trigger=trigger,
        id="spider_job",
        name="爬虫任务",
        replace_existing=True,
        max_instances=1,  # 同一时间只允许一个任务实例运行
        misfire_grace_time=300,  # 如果任务错过了执行时间，允许在5分钟内执行
    )
    
    # 启动调度器
    scheduler.start()
    logger.info("调度器已启动，等待执行任务...")
    
    try:
        # 保持程序运行
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止调度器...")
        scheduler.shutdown()
        logger.info("调度器已停止")


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

