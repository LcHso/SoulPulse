"""
SoulPulse 帖子模型

定义 AI 角色发布的帖子/动态数据结构，包括：
- 内容信息：媒体 URL、文案
- 关联关系：所属 AI 角色
- 社交数据：点赞数、密友标识
- 审核状态：待审核/已发布/已拒绝

内容审核工作流：
- status=0: 待审核，需要管理员审核后才能公开
- status=1: 已发布，在信息流中可见
- status=2: 已拒绝，不公开显示

密友功能：
- is_close_friend=True: 仅对高亲密度用户可见
- is_close_friend=False: 对所有关注用户可见
"""

from datetime import datetime

from sqlalchemy import String, Integer, Text, Boolean, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from core.database import Base


class Post(Base):
    """
    AI 角色帖子数据模型

    AI 角色发布的内容，类似 Instagram 的帖子形式。
    包含图片/视频媒体和文案内容。

    表名: posts

    字段说明:
        id: 帖子唯一标识（自增主键）
        ai_id: 所属 AI 角色 ID（外键）
        media_url: 媒体文件 URL（图片/视频）
        caption: 文案内容
        like_count: 点赞数
        is_close_friend: 是否密友专属
        status: 审核状态（0=待审核, 1=已发布, 2=已拒绝）
        memory_echo_refs: 记忆回响引用的记忆 ID 列表（JSON，用于分析）
        emotion_snapshot: 生成帖子时的 5D 情绪快照（JSON）
        trigger_type: 触发类型（scheduled/happy_post/moody_story/memory_echo/gem_request）
        created_at: 发布时间
    """
    __tablename__ = "posts"

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属 AI 角色 ID，建立外键关联和索引便于查询
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False, index=True)

    # ── 内容字段 ──────────────────────────────────────────
    # 媒体文件 URL：图片或视频的存储地址
    media_url: Mapped[str] = mapped_column(String(500), default="")
    # 文案内容：帖子的文字描述
    caption: Mapped[str] = mapped_column(Text, default="")
    # 帖子类型：image_only（图片帖）, text_only（纯文字帖）, quote（引用帖）
    post_type: Mapped[str] = mapped_column(String(50), default="image_only")

    # ── 社交数据字段 ──────────────────────────────────────────
    # 点赞数：统计用户点赞数量
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    # 密友标识：True=仅高亲密度用户可见, False=公开
    is_close_friend: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 审核状态字段 ──────────────────────────────────────────
    # 审核状态：0=待审核, 1=已发布, 2=已拒绝
    # 建立索引便于管理后台筛选
    status: Mapped[int] = mapped_column(Integer, default=0, index=True)

    # ── 记忆回响字段 (Memory Echo) ──────────────────────────────
    # 引用的记忆 ID 列表（JSON）：用于追踪帖子引用了哪些用户记忆
    # 格式示例：[{"memory_id": 123, "user_id": 456}, ...]
    memory_echo_refs: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    # 生成帖子时的 5D 情绪快照（JSON）：记录生成瞬间的情绪状态
    # 格式示例：{"energy": 80, "pleasure": 0.5, "activation": 0.3, "longing": 0.2, "security": 0.7}
    emotion_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)
    # 触发类型：scheduled（定时）/ happy_post（快乐帖）/ moody_story（情绪故事）
    #           / memory_echo（记忆回响）/ gem_request（宝石请求）
    trigger_type: Mapped[str] = mapped_column(String(20), default="scheduled")

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())