"""
SoulPulse 亲密度分层配置解析与响应验证服务

================================================================================
功能概述
================================================================================
本模块提供亲密度等级配置的解析和 AI 回复验证功能：

- IntimacyConfigResolver: 根据亲密度分数解析对应的等级配置
  - 启动时从数据库加载所有等级配置到内存缓存
  - 提供同步 resolve() 方法，供 _build_boundary_constraints 等同步函数调用
  - 支持热重载（reload()）以响应管理后台的配置修改

- validate_response(): 根据等级配置验证和修正 AI 回复
  - 长度截断（超过 max_reply_chars 则截断）
  - 禁止词检测（命中则返回 None，提示重新生成）
  - emoji 策略执行（根据 emoji_policy 移除多余 emoji）
  - 动作描写过滤（action_desc=false 时移除全角括号描写）

================================================================================
设计理念
================================================================================
1. 缓存优先：配置数据变化不频繁（通常由运营在后台调整），使用内存缓存
   避免每次聊天都查询数据库。
2. 同步兼容：resolve() 是同步方法，因为 _build_boundary_constraints() 和
   _get_generation_params() 都是同步函数，不方便改为 async。
3. 优雅降级：如果缓存为空（未初始化），resolve() 会使用内置的硬编码默认值，
   确保系统不会因为配置加载失败而崩溃。

================================================================================
主要组件
================================================================================
- IntimacyConfigResolver: 配置解析器（单例模式）
  - initialize(): 从数据库加载配置到缓存
  - resolve(): 根据分数返回对应等级配置
  - reload(): 强制重新从数据库加载
  - get_all_configs(): 返回所有等级配置
- validate_response(): 响应验证函数
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── 内存缓存中的配置数据类 ──────────────────────────────────────

@dataclass
class LevelConfigData:
    """
    亲密度等级配置的内存缓存数据结构。

    从 IntimacyLevelConfig ORM 模型中提取关键字段，
    作为纯 Python 对象避免数据库依赖。
    """
    level_id: int
    level_name: str
    level_name_cn: str
    min_score: float
    max_score: float
    temperature: float
    max_tokens: int
    top_p: float
    min_reply_chars: int
    max_reply_chars: int
    emoji_policy: str = "none"
    action_desc: bool = False
    forbidden_words: list[str] = field(default_factory=list)
    allowed_affection: list[str] = field(default_factory=list)
    proactive_cooldown_hours: int = 24


# ── 内置默认配置（缓存未初始化时的降级方案）──────────────────────

_DEFAULT_CONFIGS: list[LevelConfigData] = [
    LevelConfigData(
        level_id=0, level_name="stranger", level_name_cn="陌生人",
        min_score=0.0, max_score=2.9,
        temperature=0.55, max_tokens=64, top_p=0.85,
        min_reply_chars=1, max_reply_chars=20,
        emoji_policy="none", action_desc=False,
        forbidden_words=[
            "亲爱的", "宝贝", "想你", "爱你",
            "honey", "baby", "darling", "love you", "miss you",
            "sweetheart", "babe", "my dear", "小傻瓜",
        ],
        allowed_affection=[],
        proactive_cooldown_hours=999,
    ),
    LevelConfigData(
        level_id=1, level_name="acquaintance", level_name_cn="熟人",
        min_score=3.0, max_score=4.9,
        temperature=0.65, max_tokens=150, top_p=0.88,
        min_reply_chars=20, max_reply_chars=60,
        emoji_policy="none", action_desc=False,
        forbidden_words=[
            "宝贝", "亲爱的", "想你", "爱你",
            "baby", "darling", "love you", "sweetheart", "babe",
        ],
        allowed_affection=[],
        proactive_cooldown_hours=72,
    ),
    LevelConfigData(
        level_id=2, level_name="friend", level_name_cn="朋友",
        min_score=5.0, max_score=5.9,
        temperature=0.75, max_tokens=300, top_p=0.90,
        min_reply_chars=40, max_reply_chars=150,
        emoji_policy="moderate", action_desc=True,
        forbidden_words=["爱你", "love you"],
        allowed_affection=["笨蛋", "小傻瓜", "傻乎乎"],
        proactive_cooldown_hours=24,
    ),
    LevelConfigData(
        level_id=3, level_name="close_friend", level_name_cn="挚友",
        min_score=6.0, max_score=6.9,
        temperature=0.82, max_tokens=400, top_p=0.92,
        min_reply_chars=60, max_reply_chars=200,
        emoji_policy="moderate", action_desc=True,
        forbidden_words=[],
        allowed_affection=[
            "宝贝", "亲爱的", "笨蛋", "小傻瓜", "honey", "sweetheart",
        ],
        proactive_cooldown_hours=24,
    ),
    LevelConfigData(
        level_id=4, level_name="confidant", level_name_cn="密友",
        min_score=7.0, max_score=8.9,
        temperature=0.85, max_tokens=500, top_p=0.93,
        min_reply_chars=80, max_reply_chars=300,
        emoji_policy="unlimited", action_desc=True,
        forbidden_words=[],
        allowed_affection=[
            "宝贝", "亲爱的", "笨蛋", "小傻瓜",
            "honey", "sweetheart", "my love", "darling",
        ],
        proactive_cooldown_hours=12,
    ),
    LevelConfigData(
        level_id=5, level_name="soulmate", level_name_cn="灵魂伴侣",
        min_score=9.0, max_score=10.0,
        temperature=0.92, max_tokens=600, top_p=0.95,
        min_reply_chars=100, max_reply_chars=600,
        emoji_policy="unlimited", action_desc=True,
        forbidden_words=[],
        allowed_affection=[
            "宝贝", "亲爱的", "笨蛋", "小傻瓜",
            "honey", "sweetheart", "my love", "darling",
            "老公", "老婆",
        ],
        proactive_cooldown_hours=8,
    ),
]


# ── 亲密度配置解析器 ─────────────────────────────────────────────

class IntimacyConfigResolver:
    """
    亲密度等级配置解析器（单例模式）。

    负责管理等级配置的内存缓存，并根据亲密度分数查找对应等级。

    使用示例：
        resolver = IntimacyConfigResolver()
        await resolver.initialize(db)
        config = resolver.resolve(5.5)
        # config.level_name == "friend"
    """

    _instance: Optional[IntimacyConfigResolver] = None
    _configs: list[LevelConfigData]
    _initialized: bool = False

    def __new__(cls) -> IntimacyConfigResolver:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._configs = list(_DEFAULT_CONFIGS)
            cls._instance._initialized = False
        return cls._instance

    async def initialize(self, db) -> None:
        """
        从数据库加载所有等级配置到内存缓存。

        应在应用启动时调用（例如在 init_db() 之后）。
        如果数据库中尚无数据，将自动插入种子数据。

        Args:
            db: 异步数据库会话（AsyncSession）
        """
        try:
            from sqlalchemy import select
            from models.intimacy_level_config import IntimacyLevelConfig

            # 检查是否有数据，没有则先种子化
            result = await db.execute(
                select(IntimacyLevelConfig).order_by(IntimacyLevelConfig.level_id)
            )
            rows = list(result.scalars().all())

            if not rows:
                await self._seed_configs(db)
                result = await db.execute(
                    select(IntimacyLevelConfig).order_by(IntimacyLevelConfig.level_id)
                )
                rows = list(result.scalars().all())

            self._configs = [
                LevelConfigData(
                    level_id=row.level_id,
                    level_name=row.level_name,
                    level_name_cn=row.level_name_cn,
                    min_score=float(row.min_score),
                    max_score=float(row.max_score),
                    temperature=float(row.temperature),
                    max_tokens=row.max_tokens,
                    top_p=float(row.top_p),
                    min_reply_chars=row.min_reply_chars,
                    max_reply_chars=row.max_reply_chars,
                    emoji_policy=row.emoji_policy or "none",
                    action_desc=bool(row.action_desc),
                    forbidden_words=row.get_forbidden_words(),
                    allowed_affection=row.get_allowed_affection(),
                    proactive_cooldown_hours=row.proactive_cooldown_hours or 24,
                )
                for row in rows
            ]
            self._initialized = True
            logger.info(
                "IntimacyConfigResolver initialized with %d level configs",
                len(self._configs),
            )
        except Exception:
            logger.warning(
                "Failed to load intimacy configs from DB, using defaults",
                exc_info=True,
            )
            self._configs = list(_DEFAULT_CONFIGS)
            self._initialized = True

    async def _seed_configs(self, db) -> None:
        """
        向数据库插入种子配置数据（6 个等级）。

        Args:
            db: 异步数据库会话
        """
        from models.intimacy_level_config import IntimacyLevelConfig

        seed_data = [
            dict(
                level_id=0, level_name="stranger", level_name_cn="陌生人",
                min_score=0.0, max_score=2.9,
                temperature=0.55, max_tokens=64, top_p=0.85,
                min_reply_chars=1, max_reply_chars=20,
                emoji_policy="none", action_desc=False,
                forbidden_words=[
                    "亲爱的", "宝贝", "想你", "爱你",
                    "honey", "baby", "darling", "love you", "miss you",
                    "sweetheart", "babe", "my dear", "小傻瓜",
                ],
                allowed_affection=[],
                proactive_cooldown_hours=999,
            ),
            dict(
                level_id=1, level_name="acquaintance", level_name_cn="熟人",
                min_score=3.0, max_score=4.9,
                temperature=0.65, max_tokens=150, top_p=0.88,
                min_reply_chars=20, max_reply_chars=60,
                emoji_policy="none", action_desc=False,
                forbidden_words=[
                    "宝贝", "亲爱的", "想你", "爱你",
                    "baby", "darling", "love you", "sweetheart", "babe",
                ],
                allowed_affection=[],
                proactive_cooldown_hours=72,
            ),
            dict(
                level_id=2, level_name="friend", level_name_cn="朋友",
                min_score=5.0, max_score=5.9,
                temperature=0.75, max_tokens=300, top_p=0.90,
                min_reply_chars=40, max_reply_chars=150,
                emoji_policy="moderate", action_desc=True,
                forbidden_words=["爱你", "love you"],
                allowed_affection=["笨蛋", "小傻瓜", "傻乎乎"],
                proactive_cooldown_hours=24,
            ),
            dict(
                level_id=3, level_name="close_friend", level_name_cn="挚友",
                min_score=6.0, max_score=6.9,
                temperature=0.82, max_tokens=400, top_p=0.92,
                min_reply_chars=60, max_reply_chars=200,
                emoji_policy="moderate", action_desc=True,
                forbidden_words=[],
                allowed_affection=[
                    "宝贝", "亲爱的", "笨蛋", "小傻瓜", "honey", "sweetheart",
                ],
                proactive_cooldown_hours=24,
            ),
            dict(
                level_id=4, level_name="confidant", level_name_cn="密友",
                min_score=7.0, max_score=8.9,
                temperature=0.85, max_tokens=500, top_p=0.93,
                min_reply_chars=80, max_reply_chars=300,
                emoji_policy="unlimited", action_desc=True,
                forbidden_words=[],
                allowed_affection=[
                    "宝贝", "亲爱的", "笨蛋", "小傻瓜",
                    "honey", "sweetheart", "my love", "darling",
                ],
                proactive_cooldown_hours=12,
            ),
            dict(
                level_id=5, level_name="soulmate", level_name_cn="灵魂伴侣",
                min_score=9.0, max_score=10.0,
                temperature=0.92, max_tokens=600, top_p=0.95,
                min_reply_chars=100, max_reply_chars=600,
                emoji_policy="unlimited", action_desc=True,
                forbidden_words=[],
                allowed_affection=[
                    "宝贝", "亲爱的", "笨蛋", "小傻瓜",
                    "honey", "sweetheart", "my love", "darling",
                    "老公", "老婆",
                ],
                proactive_cooldown_hours=8,
            ),
        ]

        for data in seed_data:
            config = IntimacyLevelConfig(**data)
            db.add(config)

        await db.commit()
        logger.info("Seeded %d intimacy level configs", len(seed_data))

    def resolve(self, intimacy_score: float) -> LevelConfigData:
        """
        根据亲密度分数查找对应的等级配置。

        使用 min_score / max_score 区间匹配。如果分数超出范围（<0 或 >10），
        会被钳制到 [0.0, 10.0] 内。

        Args:
            intimacy_score: 亲密度分数 (0.0-10.0)

        Returns:
            LevelConfigData: 匹配等级的配置数据
        """
        score = max(0.0, min(10.0, float(intimacy_score)))

        for config in self._configs:
            if config.min_score <= score <= config.max_score:
                return config

        # 兜底：如果没有匹配到（理论上不应发生），返回最接近的配置
        # 按 level_id 降序找第一个 min_score <= score 的
        for config in reversed(self._configs):
            if score >= config.min_score:
                return config

        # 最终兜底：返回第一个配置（陌生人）
        return self._configs[0] if self._configs else _DEFAULT_CONFIGS[0]

    async def reload(self, db) -> None:
        """
        强制重新从数据库加载所有配置。

        当管理后台修改了配置后调用此方法以更新缓存。

        Args:
            db: 异步数据库会话
        """
        self._initialized = False
        await self.initialize(db)

    def get_all_configs(self) -> list[LevelConfigData]:
        """
        返回所有等级配置的副本。

        Returns:
            list[LevelConfigData]: 所有等级配置列表
        """
        return list(self._configs)

    @property
    def is_initialized(self) -> bool:
        """配置是否已从数据库加载。"""
        return self._initialized


# ── 模块级单例 ──────────────────────────────────────────────────

resolver = IntimacyConfigResolver()


# ── 响应验证函数 ──────────────────────────────────────────────────

# Emoji 正则表达式（覆盖大部分 Unicode emoji 范围）
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001f926-\U0001f937"
    "\U00010000-\U0010ffff"
    "\u2600-\u2B55"
    "\u200d"
    "\u23cf"
    "\u23e9"
    "\u231a"
    "\ufe0f"
    "\u3030"
    "]+",
    flags=re.UNICODE,
)

# 全角括号动作描写正则：匹配 （动作描写）
_ACTION_DESC_RE = re.compile(r"（[^）]*）")


def validate_response(
    response_text: str,
    level_config: LevelConfigData,
) -> Optional[str]:
    """
    根据亲密度等级配置验证和修正 AI 回复。

    验证流程（按顺序执行）：
    1. 长度截断：超过 max_reply_chars 则在合适的断句处截断
    2. 禁止词检测：命中任何禁止词则返回 None（需要重新生成）
    3. emoji 策略执行：根据 emoji_policy 移除或限制 emoji
    4. 动作描写过滤：action_desc=false 时移除全角括号描写

    Args:
        response_text: AI 生成的原始回复文本
        level_config: 当前亲密度等级的配置

    Returns:
        Optional[str]: 验证/修正后的回复文本。
                       返回 None 表示回复包含禁止词，需要重新生成。
    """
    if not response_text:
        return response_text

    text = response_text

    # ── 步骤 1: 长度截断 ──────────────────────────────────────
    max_chars = level_config.max_reply_chars
    if len(text) > max_chars:
        # 尝试在句号、感叹号、问号处截断
        truncated = text[:max_chars]
        # 查找最后一个句子结束符
        for sep in ("。", "！", "？", ".", "!", "?", "\n"):
            last_sep = truncated.rfind(sep)
            if last_sep > max_chars // 2:  # 至少保留一半长度
                truncated = truncated[: last_sep + 1]
                break
        else:
            # 没找到句子分隔符，直接在逗号/空格处截断
            for sep in ("，", ",", " "):
                last_sep = truncated.rfind(sep)
                if last_sep > max_chars // 2:
                    truncated = truncated[:last_sep]
                    break

        text = truncated.rstrip()

    # ── 步骤 2: 禁止词检测 ──────────────────────────────────────
    forbidden_words = level_config.forbidden_words
    if forbidden_words:
        for word in forbidden_words:
            if word and word in text:
                logger.debug(
                    "Forbidden word '%s' detected in response (level %d: %s)",
                    word, level_config.level_id, level_config.level_name,
                )
                return None  # 命中禁止词，需要重新生成

    # ── 步骤 3: emoji 策略执行 ──────────────────────────────────
    emoji_policy = level_config.emoji_policy

    if emoji_policy == "none":
        # 完全移除所有 emoji
        text = _EMOJI_RE.sub("", text)
    elif emoji_policy == "rare":
        # 最多保留 1 个 emoji
        emojis_found = list(_EMOJI_RE.finditer(text))
        if len(emojis_found) > 1:
            # 保留第一个 emoji，移除其余的
            for match in reversed(emojis_found[1:]):
                text = text[: match.start()] + text[match.end():]
    elif emoji_policy == "moderate":
        # 最多保留 3 个 emoji
        emojis_found = list(_EMOJI_RE.finditer(text))
        if len(emojis_found) > 3:
            for match in reversed(emojis_found[3:]):
                text = text[: match.start()] + text[match.end():]
    # "unlimited" — 不做任何处理

    # ── 步骤 4: 动作描写过滤 ──────────────────────────────────────
    if not level_config.action_desc:
        # 移除所有全角括号动作描写：（xxx）
        text = _ACTION_DESC_RE.sub("", text)
        # 清理可能留下的多余空格
        text = re.sub(r"\s{2,}", " ", text).strip()

    # 最终清理：移除可能产生的空行
    text = text.strip()

    return text
