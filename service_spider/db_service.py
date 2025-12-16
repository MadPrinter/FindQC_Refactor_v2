"""
数据库服务

处理商品数据的数据库操作。
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
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
    async def check_and_update_existing_product(
        session: AsyncSession,
        findqc_id: int,
        last_qc_time: Optional[datetime],
        qc_count_30days: int,
    ) -> Tuple[Optional[Product], str]:
        """
        检查现有商品并决定更新策略
        
        Args:
            session: 数据库会话
            findqc_id: FindQC 商品ID
            last_qc_time: 最新的 QC 图时间
            qc_count_30days: 30天内的 QC 图数量
            
        Returns:
            Tuple[Optional[Product], str]:
                - Product 对象（如果存在）或 None（如果不存在）
                - 操作类型："exists_updated"（存在且已更新）、"exists_deleted"（存在且已软删除）、"not_exists"（不存在）
        """
        # 查询是否已存在
        stmt = select(Product).where(Product.findqc_id == findqc_id)
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
        
        if not product:
            return None, "not_exists"
        
        # 如果商品已存在，检查最新的 QC 图是否在近30天内
        if last_qc_time is None:
            # 如果没有 QC 图时间，软删除
            product.status = 1
            product.last_update = datetime.utcnow()
            logger.info(f"商品 findqc_id={findqc_id} 已存在但无 QC 图时间，软删除")
            await session.flush()
            return product, "exists_deleted"
        
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        if last_qc_time >= thirty_days_ago:
            # 在30天内，只更新 QC 相关字段
            product.last_qc_time = last_qc_time
            product.qc_count_30days = qc_count_30days
            product.last_update = datetime.utcnow()
            logger.info(f"商品 findqc_id={findqc_id} 已存在，QC 图在30天内，只更新 QC 相关字段")
            await session.flush()
            return product, "exists_updated"
        else:
            # 不在30天内，软删除
            product.status = 1
            product.last_update = datetime.utcnow()
            logger.info(f"商品 findqc_id={findqc_id} 已存在，QC 图不在30天内，软删除")
            await session.flush()
            return product, "exists_deleted"
    
    @staticmethod
    async def save_or_update_product(
        session: AsyncSession,
        product_data: Dict[str, Any],
        update_task_id: int,
    ) -> Product:
        """
        保存新商品数据（仅用于新商品）
        
        Args:
            session: 数据库会话
            product_data: 商品数据字典
            update_task_id: 任务批次ID
            
        Returns:
            Product: 保存的商品对象
        """
        findqc_id = product_data["findqc_id"]
        
        # 创建新商品
        product = Product(**product_data, update_task_id=update_task_id)
        product.last_update = datetime.utcnow()
        session.add(product)
        logger.debug(f"创建新商品: findqc_id={findqc_id}")
        
        await session.flush()  # 获取 ID
        return product
    
    @staticmethod
    async def get_resume_category_id(
        session: AsyncSession,
        today_task_id: int,
    ) -> Optional[int]:
        """
        获取断点续传的起始分类ID
        
        查询数据库中最大的 categoryId，并检查该 categoryId 对应的商品的 
        update_task_id 是否为今天。如果是，则返回该 categoryId 用于断点续传。
        
        Args:
            session: 数据库会话
            today_task_id: 今天的任务批次ID（格式：YYYYMMDD）
            
        Returns:
            Optional[int]: 如果满足条件，返回最大的 categoryId；否则返回 None
        """
        try:
            # 查询最大的 categoryId（排除 NULL 和软删除的商品）
            stmt = (
                select(func.max(Product.categoryId))
                .where(Product.categoryId.isnot(None))
                .where(Product.status == 0)  # 只考虑未软删除的商品
            )
            result = await session.execute(stmt)
            max_category_id = result.scalar_one_or_none()
            
            if max_category_id is None:
                logger.info("数据库中没有有效的 categoryId，将从配置的起始分类开始")
                return None
            
            # 检查该 categoryId 对应的商品是否有今天的 update_task_id
            check_stmt = (
                select(Product)
                .where(Product.categoryId == max_category_id)
                .where(Product.update_task_id == today_task_id)
                .where(Product.status == 0)
                .limit(1)
            )
            check_result = await session.execute(check_stmt)
            product_with_today_task = check_result.scalar_one_or_none()
            
            if product_with_today_task:
                logger.info(
                    f"找到断点续传位置：最大 categoryId={max_category_id}，"
                    f"update_task_id={today_task_id} 为今天，将从该分类重新开始"
                )
                return max_category_id
            else:
                logger.info(
                    f"最大 categoryId={max_category_id} 对应的商品 update_task_id 不是今天，"
                    f"将从配置的起始分类开始"
                )
                return None
                
        except Exception as e:
            logger.error(f"查询断点续传分类ID失败: {e}")
            return None
    
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
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
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
            Tuple[Optional[Dict], bool]: 
                - 第一个元素：商品数据字典（如果有效）或 None（如果无效）
                - 第二个元素：是否应该保存（True=保存, False=跳过）
        """
        detail_data = detail_response.get("data", {}).get("data", {})
        
        # 提取基础信息
        price = detail_data.get("price")
        # 价格字段改为 Text 类型，直接存储原始字符串
        if price is not None:
            price = str(price)  # 转换为字符串存储
        
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
        
        # 检查过滤条件：必须有 QC 图，且最晚时间在30天内
        should_save = True
        skip_reason = None
        
        # 条件1：必须有 QC 图
        if not qc_images:
            should_save = False
            skip_reason = "没有 QC 图"
            logger.debug(f"跳过商品 findqc_id={findqc_id}: {skip_reason}")
        
        # 条件2：QC 图最晚时间必须在近30天内
        elif last_qc_time is None:
            should_save = False
            skip_reason = "无法获取 QC 图时间戳"
            logger.debug(f"跳过商品 findqc_id={findqc_id}: {skip_reason}")
        else:
            # 计算30天前的时间
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            
            if last_qc_time < thirty_days_ago:
                should_save = False
                skip_reason = f"QC 图最晚时间不在30天内 (last_qc_time={last_qc_time}, 30天前={thirty_days_ago})"
                logger.debug(f"跳过商品 findqc_id={findqc_id}: {skip_reason}")
        
        if not should_save:
            return None, False
        
        # 计算30天内的 QC 图数量
        qc_count_30days = 0
        if last_qc_time and all_qc_times:
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            # 统计所有在30天内的 QC 图数量
            for qc_time in all_qc_times:
                try:
                    # 判断时间戳是秒还是毫秒
                    timestamp = qc_time
                    if timestamp > 10**10:
                        timestamp = timestamp / 1000
                    
                    qc_datetime = datetime.fromtimestamp(timestamp)
                    if qc_datetime >= thirty_days_ago:
                        qc_count_30days += 1
                except (ValueError, TypeError, OSError):
                    continue
        
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
            "qc_count_30days": qc_count_30days,
            "status": 0,
        }
        
        return product_data, True

