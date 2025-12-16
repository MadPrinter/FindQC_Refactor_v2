"""
数据库模型定义

所有数据库表的 SQLAlchemy 模型定义。
遵循 docs/db_structure.dbml 中的数据库设计。
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import (
    Integer,
    Text,
    String,
    Float,
    DateTime,
    JSON,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import DATETIME


class Base(DeclarativeBase):
    """SQLAlchemy 基础类"""
    pass


class Product(Base):
    """
    商品主表 (t_products)
    
    存储从 FindQC 平台爬取的商品基本信息。
    """
    __tablename__ = "t_products"
    
    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    
    # 基础信息
    findqc_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, comment="findqc平台的原始ID")
    itemId: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="商品外部ID")
    mallType: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="商城类型")
    categoryId: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="商品类型ID")
    price: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="商品价格")
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="商品质量kg")
    
    # 图片信息（JSON格式存储）
    image_urls: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="原始图片url列表 JSON格式: {qc_images: [], main_images: [], sku_images: []}"
    )
    
    # 爬虫与任务状态
    last_qc_time: Mapped[Optional[datetime]] = mapped_column(
        DATETIME, nullable=True, comment="质检图中最晚的时间戳对应的时间"
    )
    qc_count_30days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="30天质检图数量")
    introduce: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="qwen大模型生成的商品简介")
    pic_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="选出的一张参与聚类的商品图片")
    update_task_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="关联的任务批次ID")
    last_update: Mapped[Optional[datetime]] = mapped_column(DATETIME, nullable=True, comment="最后更新时间")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="0:保留, 1:软删除")
    
    # 关系
    tags: Mapped["ProductTag"] = relationship("ProductTag", back_populates="product", uselist=False)
    tasks: Mapped[list["TaskProduct"]] = relationship("TaskProduct", back_populates="product")
    
    # 索引：itemId + mallType 构成唯一的商品业务标识
    # MySQL 8.0 要求 TEXT 类型列创建索引时指定键长度
    __table_args__ = (
        Index("idx_item_mall", "itemId", "mallType", mysql_length={"itemId": 255}),
    )
    
    def __repr__(self) -> str:
        return f"<Product(id={self.id}, findqc_id={self.findqc_id}, itemId={self.itemId})>"


class TaskProduct(Base):
    """
    任务关联表 (t_tasks_products)
    
    记录商品处理任务的状态。
    """
    __tablename__ = "t_tasks_products"
    
    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    
    # 外键关联
    findqc_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_products.findqc_id", ondelete="CASCADE"),
        nullable=False,
        comment="关联商品表的findqc_id"
    )
    update_task_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="关联的任务批次ID")
    
    # 状态
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="0:待执行, 1:完成")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DATETIME, default=datetime.utcnow, nullable=False, comment="创建时间"
    )
    
    # 关系
    product: Mapped["Product"] = relationship("Product", back_populates="tasks")
    
    def __repr__(self) -> str:
        return f"<TaskProduct(id={self.id}, findqc_id={self.findqc_id}, status={self.status})>"


class ProductTag(Base):
    """
    AI 标签表 (t_product_tags)
    
    存储由 Qwen 大模型和 Google Lens 生成的商品标签信息。
    与商品表一对一关联。
    """
    __tablename__ = "t_product_tags"
    
    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    
    # 外键关联（一对一）
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("t_products.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="关联商品表的id，一对一关系"
    )
    
    # AI 分析结果（由 Qwen 大模型生成）
    category: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="AI 归纳的类目")
    brand: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="品牌")
    model: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="型号")
    target_audience: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="适用人群")
    season: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="季节：春夏/秋冬/四季等")
    environment: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="适用环境：室内/户外/运动等")
    
    # 时间戳
    updated_at: Mapped[Optional[datetime]] = mapped_column(DATETIME, nullable=True, comment="最后更新时间")
    
    # 关系
    product: Mapped["Product"] = relationship("Product", back_populates="tags")
    
    def __repr__(self) -> str:
        return f"<ProductTag(id={self.id}, product_id={self.product_id}, brand={self.brand})>"


class Cluster(Base):
    """
    聚类中心表 (t_cluster)
    
    存储每个聚类簇的代表商品或虚拟中心。
    """
    __tablename__ = "t_cluster"
    
    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    
    # 簇标识（使用 VARCHAR 而不是 TEXT，以支持 UNIQUE 约束）
    cluster_code: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, comment="规则: mallType_itemId (簇中心的唯一标识)"
    )
    
    # 簇中心的数据快照
    center_itemId: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="簇中心的itemId")
    center_mallType: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="簇中心的mallType")
    
    # 聚合数据
    total_sales_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="该簇所有成员销量总和")
    member_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="该簇下有多少个商品")
    
    # 时间戳
    created_at: Mapped[Optional[datetime]] = mapped_column(DATETIME, nullable=True, comment="创建时间")
    
    # 关系
    members: Mapped[list["ClusterMember"]] = relationship("ClusterMember", back_populates="cluster")
    
    def __repr__(self) -> str:
        return f"<Cluster(id={self.id}, cluster_code={self.cluster_code}, member_count={self.member_count})>"


class ClusterMember(Base):
    """
    聚类成员表 (t_cluster_members)
    
    记录哪些商品属于哪个簇。
    """
    __tablename__ = "t_cluster_members"
    
    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    
    # 外键关联（使用 VARCHAR 以匹配 t_cluster 表）
    cluster_code: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("t_cluster.cluster_code", ondelete="CASCADE"),
        nullable=False,
        comment="关联簇中心的cluster_code"
    )
    
    # 成员信息（使用 VARCHAR 以便在 UNIQUE 约束中使用）
    member_itemId: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="成员的itemId")
    member_mallType: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="成员的mallType")
    
    # 关系
    cluster: Mapped["Cluster"] = relationship("Cluster", back_populates="members")
    
    # 索引：避免同一商品重复加入同一cluster
    __table_args__ = (
        UniqueConstraint("cluster_code", "member_itemId", "member_mallType", name="uq_cluster_member"),
    )
    
    def __repr__(self) -> str:
        return f"<ClusterMember(id={self.id}, cluster_code={self.cluster_code}, itemId={self.member_itemId})>"

