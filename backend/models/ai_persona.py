from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class AIPersona(Base):
    """
    AI Persona model for chat companions.
    
    Categories:
    - otome: Male characters for female audience (乙女向)
    - bl: Male characters for BL/yaoi audience (gay向)
    - gl: Female characters for GL/yuri audience
    - general: Gender-neutral / general audience
    
    Target audience helps with recommendation and filtering.
    """
    __tablename__ = "ai_personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    bio: Mapped[str] = mapped_column(String(500), default="")
    profession: Mapped[str] = mapped_column(String(100), default="")
    personality_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    gender_tag: Mapped[str] = mapped_column(String(20), default="male")
    # Category for content filtering: otome, bl, gl, general
    category: Mapped[str] = mapped_column(String(20), default="general", index=True)
    # Personality archetype for recommendations: e.g., "温柔治愈", "高冷傲娇", "阳光开朗"
    archetype: Mapped[str] = mapped_column(String(50), default="")
    ins_style_tags: Mapped[str] = mapped_column(String(500), default="")
    # Visual description for consistent AI image generation
    visual_description: Mapped[str] = mapped_column(Text, nullable=True)
    # Visual Identity (VI) System - for face reference consistency
    # Base portrait URL - the "ID photo" for face reference
    base_face_url: Mapped[str] = mapped_column(String(500), nullable=True)
    # Fixed visual prompt tags for consistent character appearance
    # Example: "silver hair, sharp jawline, deep blue eyes, tall"
    visual_prompt_tags: Mapped[str] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Shanghai")
    # Display order for listing (lower = first)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # Soft delete / disable
    is_active: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
