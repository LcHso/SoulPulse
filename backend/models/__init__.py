"""
SoulPulse 模型包

集中导入所有 ORM 模型，保证 SQLAlchemy 元数据完整注册。
init_db() 在创建表时会引用 Base.metadata，这里的导入是保险措施，
避免出现"漏注册"导致表未被创建的问题。

新增的模型必须在此处追加导入。
"""

# 视觉系统 - 新增动漫化设计稿与 CG 收藏体系
from models.character_design import CharacterDesign  # noqa: F401
from models.cg_illustration import CGIllustration  # noqa: F401
from models.user_cg_collection import UserCGCollection  # noqa: F401

# 资产管线 - Asset Pipeline & Version Control (Plan Task 5)
from models.asset_registry import AssetRegistry  # noqa: F401

# 世界观扩展 - Worldbuilding Expansion (Plan Task 1)
from models.world_event import WorldEvent  # noqa: F401
from models.persona_relationship import PersonaRelationship  # noqa: F401
from models.character_arc import CharacterArc  # noqa: F401

# 服装与场景系统 (Plan Task 2)
from models.outfit_config import OutfitConfig, UserOutfitUnlock  # noqa: F401

# 对话场景与互动剧情 (Plan Task 3)
from models.chat_scene import ChatScene, UserSceneProgress  # noqa: F401

# 角色发布管线与轮换 (Plan Task 9.3-9.4)
from models.character_launch import (  # noqa: F401
    CharacterLaunchCampaign,
    CharacterAvailability,
)

# 商业化深化 (Plan Task 4)
from models.subscription import SubscriptionTier, UserSubscription  # noqa: F401
from models.event_campaign import EventCampaign, UserEventProgress  # noqa: F401

__all__ = [
    "CharacterDesign",
    "CGIllustration",
    "UserCGCollection",
    "AssetRegistry",
    "WorldEvent",
    "PersonaRelationship",
    "CharacterArc",
    "OutfitConfig",
    "UserOutfitUnlock",
    "ChatScene",
    "UserSceneProgress",
    "CharacterLaunchCampaign",
    "CharacterAvailability",
    "SubscriptionTier",
    "UserSubscription",
    "EventCampaign",
    "UserEventProgress",
]
