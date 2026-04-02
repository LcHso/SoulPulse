"""
SoulPulse 用户模型

定义用户账户的数据结构，包括：
- 基本信息：邮箱、密码、昵称、头像
- 偏好设置：性别、倾向偏好
- 账户状态：钻石余额、管理员权限
- 时间戳：创建时间

管理员权限说明：
- is_admin=0: 普通用户
- is_admin=1: 管理员，可访问后台管理接口
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class User(Base):
    """
    用户数据模型

    存储所有注册用户的信息，是系统的核心实体之一。
    用户可以与多个 AI 角色建立关系，进行聊天互动。

    表名: users

    字段说明:
        id: 用户唯一标识（自增主键）
        email: 登录邮箱（唯一，用于认证）
        hashed_password: bcrypt 哈希后的密码
        nickname: 用户昵称（显示名称）
        avatar_url: 头像图片 URL
        gender: 性别（not_specified/male/female）
        orientation_preference: 倾向偏好（male/female/both）
        gem_balance: 钻石余额（虚拟货币）
        is_admin: 管理员标识（0=普通用户, 1=管理员）
        created_at: 注册时间
    """
    __tablename__ = "users"

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 登录邮箱，唯一且建立索引便于快速查询
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # bcrypt 哈希后的密码，不可逆加密
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── 个人信息字段 ──────────────────────────────────────────
    # 用户昵称，默认为 "User"
    nickname: Mapped[str] = mapped_column(String(100), default="User")
    # 头像 URL，可选字段
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, default=None)
    # 性别：not_specified（未指定）, male（男）, female（女）
    gender: Mapped[str] = mapped_column(String(20), default="not_specified")
    # 倾向偏好：用于推荐匹配，male/female/both
    orientation_preference: Mapped[str] = mapped_column(String(50), default="male")

    # ── 账户状态字段 ──────────────────────────────────────────
    # 钻石余额：虚拟货币，用于付费功能（默认 100 钻石）
    gem_balance: Mapped[int] = mapped_column(Integer, default=100)
    # 管理员权限标识：0=普通用户, 1=管理员
    is_admin: Mapped[int] = mapped_column(Integer, default=0)

    # ── 时间戳字段 ──────────────────────────────────────────
    # 注册时间，数据库自动生成
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())