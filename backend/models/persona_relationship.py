"""
SoulPulse 角色关系模型

定义 AI 角色之间的人际关系图，构建可信的虚拟世界。
当用户在聊天中提到另一个角色名时，可通过该表检索"我对那个人的看法"
并注入到系统提示中，实现可信的世界观回响。

关系类型示例：
- colleague（同事）
- friend（朋友）
- rival（对手）
- crush（暗恋对象）
- childhood_friend（青梅竹马）
- bandmate（乐队成员）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class PersonaRelationship(Base):
    """
    角色间关系数据模型

    表名: persona_relationships
    """

    __tablename__ = "persona_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # 主体角色 ID（"我"）
    persona_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"))
    # 客体角色 ID（"对方"）
    persona_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"))
    # 关系类型，例如 colleague / friend / rival
    relationship_type: Mapped[str] = mapped_column(String(50))
    # 中性描述，例如 "They met at a variety show filming"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 公开语境：persona_a 在低亲密度场景对外提到 persona_b 时说的话
    public_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 私密语境：persona_a 在高亲密度场景对用户透露 persona_b 时的真实想法
    private_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
