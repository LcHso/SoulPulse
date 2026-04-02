"""
SoulPulse AI 角色模型

定义 AI 虚拟角色的数据结构，包括：
- 基本信息：名称、简介、职业、性格设定
- 视觉系统：外观描述、基础肖像、视觉标签
- 分类系统：性别标签、内容分类、性格原型
- 状态控制：排序、是否激活

分类说明：
- otome: 乙女向（面向女性用户的男性角色）
- bl: BL 向（面向 BL/腐女用户的男性角色）
- gl: GL 向（面向 GL/百合用户的女角色）
- general: 通用向（性别中立/大众向）

视觉一致性系统（Visual Identity System）：
- base_face_url: 基础肖像 URL，作为 AI 图片生成的面部参考
- visual_prompt_tags: 固定的视觉标签，确保角色外观一致
"""

from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class AIPersona(Base):
    """
    AI 角色数据模型

    SoulPulse 的核心实体，定义虚拟 AI 伴侣的所有属性。
    用户可以与不同的 AI 角色建立独特的情感关系。

    表名: ai_personas

    字段说明:
        id: 角色唯一标识（自增主键）
        name: 角色名称
        bio: 个人简介
        profession: 职业
        personality_prompt: 性格设定 Prompt（用于 LLM）
        gender_tag: 性别标签（male/female）
        category: 内容分类（otome/bl/gl/general）
        archetype: 性格原型（如"温柔治愈"、"高冷傲娇"）
        ins_style_tags: Instagram 风格标签
        visual_description: 视觉外观描述
        base_face_url: 基础肖像 URL（面部参考图）
        visual_prompt_tags: 视觉标签（确保生成一致性）
        avatar_url: 头像 URL
        timezone: 时区设置
        sort_order: 排序顺序（越小越靠前）
        is_active: 是否激活（软删除）
        created_at: 创建时间
    """
    __tablename__ = "ai_personas"

    # ── 基本信息字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 角色名称，如"陆晨曦"、"顾言深"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 个人简介，展示在角色档案页
    bio: Mapped[str] = mapped_column(String(500), default="")
    # 职业设定，如"医生"、"律师"、"艺术家"
    profession: Mapped[str] = mapped_column(String(100), default="")
    # 性格设定 Prompt，用于指导 LLM 的回复风格
    personality_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # ── 分类与标签字段 ──────────────────────────────────────────
    # 性别标签：male/female，用于筛选和推荐
    gender_tag: Mapped[str] = mapped_column(String(20), default="male")
    # 内容分类：otome（乙女）/ bl / gl / general，建立索引便于筛选
    category: Mapped[str] = mapped_column(String(20), default="general", index=True)
    # 性格原型：用于推荐匹配，如"温柔治愈"、"高冷傲娇"、"阳光开朗"
    archetype: Mapped[str] = mapped_column(String(50), default="")
    # Instagram 风格标签：用于生成帖子风格
    ins_style_tags: Mapped[str] = mapped_column(String(500), default="")

    # ── 视觉一致性系统（Visual Identity System）──────────────────────────
    # 视觉外观描述：详细的文字描述，用于 AI 图片生成
    visual_description: Mapped[str] = mapped_column(Text, nullable=True)
    # 基础肖像 URL：角色的"身份证照片"，作为面部参考
    # 用于 Wanx API 的 face_reference 参数，确保面部一致性
    base_face_url: Mapped[str] = mapped_column(String(500), nullable=True)
    # 固定视觉标签：用于每次图片生成的一致性
    # 示例："银发, 锋利下颌线, 深蓝眼眸, 高挑身材"
    visual_prompt_tags: Mapped[str] = mapped_column(Text, nullable=True)
    # 头像 URL：展示用的头像图片
    avatar_url: Mapped[str] = mapped_column(String(500), default="")

    # ── 状态控制字段 ──────────────────────────────────────────
    # 时区设置：影响主动消息发送时间
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Shanghai")
    # 排序顺序：数值越小越靠前展示
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # 是否激活：0=禁用（软删除）, 1=激活，建立索引便于筛选
    is_active: Mapped[int] = mapped_column(Integer, default=1, index=True)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())