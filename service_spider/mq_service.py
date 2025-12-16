"""
消息队列服务

处理 RabbitMQ 消息的发送。
"""

import json
from typing import Dict, Any
from datetime import datetime
import aio_pika
from loguru import logger

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from shared_lib.config import settings
except ImportError:
    # 如果直接运行，可能需要设置路径
    import os
    os.chdir(project_root)
    from shared_lib.config import settings


class MessageQueueService:
    """消息队列服务"""
    
    def __init__(self):
        """初始化消息队列服务"""
        self.connection = None
        self.channel = None
        self.exchange = None
        self._initialized = False
    
    async def initialize(self):
        """初始化 RabbitMQ 连接"""
        if self._initialized:
            return
        
        try:
            # 连接 RabbitMQ
            self.connection = await aio_pika.connect_robust(
                settings.rabbitmq_url,
                client_properties={"connection_name": "service_spider"},
            )
            self.channel = await self.connection.channel()
            
            # 声明 Exchange
            self.exchange = await self.channel.declare_exchange(
                "findqc_tasks",
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            
            # 声明队列
            queue = await self.channel.declare_queue(
                "spider.products",
                durable=True,
            )
            
            # 绑定队列到 Exchange
            await queue.bind(self.exchange, routing_key="product.new")
            
            self._initialized = True
            logger.info("RabbitMQ 连接初始化成功")
        except Exception as e:
            logger.error(f"RabbitMQ 连接初始化失败: {e}")
            raise
    
    async def close(self):
        """关闭 RabbitMQ 连接"""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("RabbitMQ 连接已关闭")
    
    async def send_product_new_message(
        self,
        task_id: int,
        findqc_id: int,
        product_id: int,
        item_id: str,
        mall_type: str,
    ) -> None:
        """
        发送商品新增消息到消息队列
        
        Args:
            task_id: 任务批次ID
            findqc_id: FindQC 商品ID
            product_id: 数据库中的商品ID
            item_id: 商品外部ID
            mall_type: 商城类型
        """
        if not self._initialized:
            await self.initialize()
        
        message_body = {
            "task_id": task_id,
            "findqc_id": findqc_id,
            "product_id": product_id,
            "itemId": item_id,
            "mallType": mall_type,
            "action": "product.new",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        
        try:
            message = aio_pika.Message(
                json.dumps(message_body).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            
            await self.exchange.publish(
                message,
                routing_key="product.new",
            )
            
            logger.debug(
                f"发送消息成功: findqc_id={findqc_id}, product_id={product_id}, "
                f"action=product.new"
            )
        except Exception as e:
            logger.error(f"发送消息失败: findqc_id={findqc_id}, error={e}")
            raise


# 全局消息队列服务实例
mq_service = MessageQueueService()

