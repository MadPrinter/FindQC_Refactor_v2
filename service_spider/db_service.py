"""
数据库服务

处理商品数据的数据库操作。
"""

from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from loguru import logger

import sys
from pathlib import Path

# 添加项目根目录到路径，以便导入 shared_lib
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared_lib.models import Product, TaskProduct


class ProductDBService:
    """商品数据库服务"""
    
    @staticmethod
    async def save_or_update_product(
        session: AsyncSession,
        product_data: Dict[str, Any],
        update_task_id: int,
    ) -> Product:
        """
        保存或更新商品数据（Upsert）
        
        Args:
            session: 数据库会话
            product_data: 商品数据字典
            update_task_id: 任务批次ID
            
        Returns:
            Product: 保存的商品对象
        """
        findqc_id = product_data["findqc_id"]
        
        # 查询是否已存在
        stmt = select(Product).where(Product.findqc_id == findqc_id)
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
        
        if product:
            # 更新现有商品
            for key, value in product_data.items():
                if hasattr(product, key):
                    setattr(product, key, value)
            product.last_update = datetime.utcnow()
            product.update_task_id = update_task_id
            logger.debug(f"更新商品: findqc_id={findqc_id}")
        else:
            # 创建新商品
            product = Product(**product_data, update_task_id=update_task_id)
            product.last_update = datetime.utcnow()
            session.add(product)
            logger.debug(f"创建商品: findqc_id={findqc_id}")
        
        await session.flush()  # 获取 ID
        return product
    
    @staticmethod
    async def create_task_record(
        session: AsyncSession,
        findqc_id: int,
        update_task_id: int,
        status: int = 0,
    ) -> TaskProduct:
        """
        创建任务记录
        
        Args:
            session: 数据库会话
            findqc_id: FindQC 商品ID
            update_task_id: 任务批次ID
            status: 任务状态（0:待执行, 1:完成）
            
        Returns:
            TaskProduct: 创建的任务对象
        """
        task = TaskProduct(
            findqc_id=findqc_id,
            update_task_id=update_task_id,
            status=status,
            created_at=datetime.utcnow(),
        )
        session.add(task)
        await session.flush()
        logger.debug(f"创建任务记录: findqc_id={findqc_id}, task_id={update_task_id}")
        return task
    
    @staticmethod
    def prepare_product_data(
        findqc_id: int,
        item_id: str,
        mall_type: str,
        category_id: int,
        detail_response: Dict[str, Any],
        atlas_responses: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        从 API 响应中提取并整理商品数据
        
        Args:
            findqc_id: FindQC 商品ID
            item_id: 商品外部ID
            mall_type: 商城类型
            category_id: 分类ID
            detail_response: 商品详情 API 响应
            atlas_responses: 图集 API 响应列表
            
        Returns:
            Dict: 整理后的商品数据字典
        """
        detail_data = detail_response.get("data", {}).get("data", {})
        
        # 提取基础信息
        price = detail_data.get("price")
        if price:
            try:
                price = float(price)
            except (ValueError, TypeError):
                price = None
        
        weight = detail_data.get("weight")
        if weight:
            try:
                weight = float(weight)
            except (ValueError, TypeError):
                weight = None
        
        # 整理图片结构
        qc_images = []
        main_images = []
        sku_images = []
        
        # 从 detail 接口获取主图和SKU图
        main_images = detail_data.get("picList", [])
        
        # 从 detail 接口获取 SKU 图
        props_list = detail_data.get("propsList", [])
        for prop in props_list:
            option_list = prop.get("optionList", [])
            for option in option_list:
                pic_url = option.get("picUrl")
                if pic_url:
                    sku_images.append(pic_url)
        
        # 从 detail 接口获取 QC 图
        qc_list = detail_data.get("qcList", [])
        for qc in qc_list:
            qc_url = qc.get("url")
            if qc_url:
                qc_images.append(qc_url)
        
        # 从 atlas 接口获取 QC 图和视频，并收集所有 QC 时间戳
        all_qc_times = []  # 收集所有 QC 图的时间戳
        
        # 先从 detail 接口的 qcList 提取时间戳
        if qc_list:
            for qc in qc_list:
                qc_time = qc.get("time")
                if qc_time is not None:
                    all_qc_times.append(qc_time)
        
        # 从 atlas 接口获取 QC 图和视频，并提取时间戳
        for atlas_response in atlas_responses:
            atlas_data = atlas_response.get("data", {})
            atlas_list = atlas_data.get("atlasList", [])
            for atlas_item in atlas_list:
                # QC 图
                atlas_qc_list = atlas_item.get("qcList", [])
                for qc in atlas_qc_list:
                    qc_url = qc.get("url")
                    if qc_url and qc_url not in qc_images:
                        qc_images.append(qc_url)
                    
                    # 提取时间戳
                    qc_time = qc.get("time")
                    if qc_time is not None:
                        all_qc_times.append(qc_time)
        
        # 获取 QC 时间（取最新的时间戳）
        last_qc_time = None
        if all_qc_times:
            try:
                # 找到最大的时间戳
                max_timestamp = max(all_qc_times)
                
                # 判断时间戳是秒还是毫秒（通常大于 10^10 的是毫秒）
                if max_timestamp > 10**10:
                    # 毫秒时间戳，转换为秒
                    max_timestamp = max_timestamp / 1000
                
                last_qc_time = datetime.fromtimestamp(max_timestamp)
            except (ValueError, TypeError, OSError) as e:
                logger.warning(f"解析 QC 时间戳失败: {e}, timestamps={all_qc_times[:5]}")
                pass
        
        # 构造图片 JSON
        image_urls = {
            "qc_images": qc_images,
            "main_images": main_images,
            "sku_images": sku_images,
        }
        
        # 构造商品数据
        product_data = {
            "findqc_id": findqc_id,
            "itemId": item_id,
            "mallType": mall_type,
            "categoryId": category_id,
            "price": price,
            "weight": weight,
            "image_urls": image_urls,
            "last_qc_time": last_qc_time,
            "qc_count_30days": len(qc_images),  # 简化处理，实际应该计算30天内的
            "status": 0,
        }
        
        return product_data

