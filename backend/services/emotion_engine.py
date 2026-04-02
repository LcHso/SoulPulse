"""
情绪状态机 - 核心引擎

================================================================================
功能概述
================================================================================
本模块提供无状态函数来管理每个用户↔AI 关系的生理状态（能量）和心理状态
（愉悦度、激活度、思念、安全感）。

================================================================================
设计理念
================================================================================
核心设计原则：
  亲密度 = 门控（AI *被允许*做什么）
  情绪   = 驱动（AI *选择*如何表现）

这意味着：
- 亲密度决定了 AI 的行为边界（能说什么、能做什么）
- 情绪决定了 AI 的行为方式（如何说话、如何反应）

================================================================================
情绪维度
================================================================================
本引擎追踪以下情绪维度：

1. 能量 (energy, 0-100)：
   - 生理状态，代表 AI 的精力水平
   - 随时间恢复（+5/小时）
   - 交互消耗（聊天 -3~-5，生成帖子 -8~-10）

2. 愉悦度 (pleasure, -1~1)：
   - 心理状态，代表心情好坏
   - 受交互影响（关心 +0.10，普通聊天 +0.05）
   - 随时间衰减趋向 0

3. 激活度 (activation, -1~1)：
   - 心理状态，代表情绪活跃程度
   - 高激活 = 情绪高涨、兴奋
   - 低激活 = 情绪低落、消沉

4. 思念 (longing, 0-1)：
   - 代表对用户的思念程度
   - 随时间增长（+0.03/小时）
   - 交互后降低

5. 安全感 (security, -1~1)：
   - 代表关系的安全感程度
   - 低安全感 = 不安、需要确认
   - 高安全感 = 信任、稳定

================================================================================
主要组件
================================================================================
- get_or_create(): 获取或创建情绪状态
- apply_time_decay(): 应用时间衰减效果
- apply_interaction(): 应用交互效果
- classify_chat_event(): 分类聊天事件类型
- build_emotion_directive(): 构建情绪指令提示词
- get_param_overrides(): 获取生成参数覆盖
- check_proactive_triggers(): 检查主动触发条件
- build_emotion_hint(): 构建前端 UI 情绪提示
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.emotion_state import EmotionState

logger = logging.getLogger(__name__)

# ── 新关系的默认情绪维度值 ────────────────────────
DEFAULT_ENERGY = 80.0        # 默认能量：较高
DEFAULT_PLEASURE = 0.3       # 默认愉悦度：略积极
DEFAULT_ACTIVATION = 0.2     # 默认激活度：略活跃
DEFAULT_LONGING = 0.0        # 默认思念：无
DEFAULT_SECURITY = 0.5       # 默认安全感：中等

# ── 关怀意图关键词列表（热路径，不调用 LLM）─────────────────
# 这些关键词用于快速检测用户的关心意图，触发特殊的情绪响应
_CARING_KEYWORDS_ZH = (
    "早睡", "晚安", "好好休息", "注意身体", "别太累", "照顾好自己",
    "心疼", "辛苦了", "早点睡", "多喝水", "保重", "别熬夜", "好好吃饭",
)
_CARING_KEYWORDS_EN = (
    "rest well", "good night", "take care", "don't overwork",
    "sleep well", "get some rest", "take it easy",
    "look after yourself", "don't stay up",
)

# 时间衰减计算的最大小时数（防止长时间不活跃后的极端波动）
_MAX_DECAY_HOURS = 168  # 1 周


# ── 数值约束函数 ────────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    """
    将数值约束在指定范围内。

    Args:
        value: 待约束的值
        lo: 下限
        hi: 上限

    Returns:
        float: 约束后的值
    """
    return max(lo, min(hi, value))


def _clamp_state(s: EmotionState) -> EmotionState:
    """
    约束情绪状态的所有维度到有效范围。

    Args:
        s: 情绪状态对象

    Returns:
        EmotionState: 约束后的情绪状态
    """
    s.energy = _clamp(s.energy, 0.0, 100.0)
    s.pleasure = _clamp(s.pleasure, -1.0, 1.0)
    s.activation = _clamp(s.activation, -1.0, 1.0)
    s.longing = _clamp(s.longing, 0.0, 1.0)
    s.security = _clamp(s.security, -1.0, 1.0)
    return s


# ── 核心函数 ──────────────────────────────────────────────────

async def get_or_create(
    db: AsyncSession, user_id: int, ai_id: int,
) -> EmotionState:
    """
    加载用户↔AI 对的情绪状态，应用时间衰减。

    如果不存在则创建带有温暖默认值的新记录。

    Args:
        db: 异步数据库会话
        user_id: 用户 ID
        ai_id: AI 人格 ID

    Returns:
        EmotionState: 情绪状态对象
    """
    result = await db.execute(
        select(EmotionState).where(
            EmotionState.user_id == user_id,
            EmotionState.ai_id == ai_id,
        )
    )
    state = result.scalar_one_or_none()

    if state is not None:
        # 存在记录，应用时间衰减后返回
        apply_time_decay(state)
        return state

    # 不存在记录，创建新的情绪状态
    state = EmotionState(
        user_id=user_id,
        ai_id=ai_id,
        energy=DEFAULT_ENERGY,
        pleasure=DEFAULT_PLEASURE,
        activation=DEFAULT_ACTIVATION,
        longing=DEFAULT_LONGING,
        security=DEFAULT_SECURITY,
    )
    db.add(state)
    await db.flush()
    return state


def apply_time_decay(state: EmotionState) -> EmotionState:
    """
    应用自上次交互以来的被动时间变化。

    时间衰减效果：
    - 能量恢复（+5/小时）：休息恢复精力
    - 愉悦度和激活度衰减：趋向 0 的乘法衰减
    - 思念增长（+0.03/小时）：越久没联系越想念
    - 安全感略微下降（-0.003/小时）：长期不联系会产生不安

    衰减时间上限为 168 小时（1 周），防止极端波动。

    Args:
        state: 情绪状态对象

    Returns:
        EmotionState: 应用衰减后的情绪状态
    """
    now = datetime.now(timezone.utc)
    last = state.last_interaction_at
    if last is None:
        state.last_interaction_at = now
        return _clamp_state(state)

    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    elapsed_seconds = (now - last).total_seconds()
    if elapsed_seconds <= 0:
        return state

    hours = min(elapsed_seconds / 3600.0, _MAX_DECAY_HOURS)

    # 生理状态：休息恢复能量
    state.energy += 5.0 * hours

    # 心理状态：愉悦度和激活度乘法衰减趋向 0
    state.pleasure *= 0.98 ** hours
    state.activation *= 0.95 ** hours

    # 思念随时间增长
    state.longing += 0.03 * hours

    # 安全感略微下降
    state.security -= 0.003 * hours

    state.last_interaction_at = now
    return _clamp_state(state)


# ── 交互效果矩阵 ─────────────────────────────────────────────

# 效果矩阵：(能量, 愉悦度, 激活度, 思念模式, 思念值, 安全感)
# longing_mode: "mul" = 乘法降低当前思念, "add" = 加法变化
_EFFECTS: dict[str, dict] = {
    "chat": {
        # 普通聊天：消耗少量能量，略微提升愉悦和激活，大幅降低思念
        "energy": -3, "pleasure": 0.05, "activation": 0.05,
        "longing_mode": "mul", "longing_val": 0.5, "security": 0.02,
    },
    "chat_long": {
        # 长聊天：消耗更多能量，提升愉悦，大幅降低思念
        "energy": -5, "pleasure": 0.05, "activation": 0.03,
        "longing_mode": "mul", "longing_val": 0.3, "security": 0.02,
    },
    "chat_caring": {
        # 关心类聊天：恢复能量，大幅提升愉悦和安全，极度降低思念
        "energy": 12, "pleasure": 0.10, "activation": -0.05,
        "longing_mode": "mul", "longing_val": 0.2, "security": 0.08,
    },
    "comment": {
        # 评论互动：消耗少量能量，略微提升愉悦和安全
        "energy": -1, "pleasure": 0.03, "activation": 0.02,
        "longing_mode": "add", "longing_val": -0.05, "security": 0.02,
    },
    "like": {
        # 点赞：无能量消耗，提升愉悦和安全
        "energy": 0, "pleasure": 0.05, "activation": 0.01,
        "longing_mode": "add", "longing_val": -0.03, "security": 0.03,
    },
    "generate_post": {
        # 生成帖子：消耗较多能量
        "energy": -8, "pleasure": 0, "activation": 0.02,
        "longing_mode": "add", "longing_val": 0, "security": 0,
    },
    "generate_story": {
        # 生成 Story：消耗更多能量
        "energy": -10, "pleasure": 0, "activation": 0.03,
        "longing_mode": "add", "longing_val": 0, "security": 0,
    },
}


def apply_interaction(
    state: EmotionState,
    event: str,
    metadata: dict | None = None,
) -> EmotionState:
    """
    根据交互事件更新情绪维度。

    Args:
        state: 情绪状态对象
        event: 事件类型（chat, chat_long, chat_caring, comment, like 等）
        metadata: 事件元数据（可选，暂未使用）

    Returns:
        EmotionState: 更新后的情绪状态
    """
    fx = _EFFECTS.get(event)
    if fx is None:
        logger.warning("Unknown emotion event: %s", event)
        return state

    # 应用各维度效果
    state.energy += fx["energy"]
    state.pleasure += fx["pleasure"]
    state.activation += fx["activation"]
    state.security += fx["security"]

    # 思念可以是乘法或加法变化
    if fx["longing_mode"] == "mul":
        state.longing *= fx["longing_val"]
    else:
        state.longing += fx["longing_val"]

    state.last_interaction_at = datetime.now(timezone.utc)
    return _clamp_state(state)


# ── 关怀意图检测（关键词匹配，不调用 LLM）─────────────────────

def detect_caring_intent(message: str) -> bool:
    """
    检测消息是否包含关心/休息相关的关键词。

    这是一个热路径函数，不调用 LLM，直接通过关键词匹配判断。

    Args:
        message: 用户消息

    Returns:
        bool: 是否包含关怀意图
    """
    lower = message.lower()
    for kw in _CARING_KEYWORDS_ZH:
        if kw in message:
            return True
    for kw in _CARING_KEYWORDS_EN:
        if kw in lower:
            return True
    return False


def classify_chat_event(message: str) -> str:
    """
    将用户聊天消息分类为情绪事件类型。

    分类逻辑：
    1. 如果包含关怀关键词 → "chat_caring"
    2. 如果消息长度 > 100 → "chat_long"
    3. 否则 → "chat"

    Args:
        message: 用户消息

    Returns:
        str: 情绪事件类型
    """
    if detect_caring_intent(message):
        return "chat_caring"
    if len(message) > 100:
        return "chat_long"
    return "chat"


# ── 提示词指令生成 ─────────────────────────────────────

def _energy_label(energy: float) -> str:
    """将能量值转换为自然语言标签。"""
    if energy < 20:
        return "exhausted"
    if energy < 40:
        return "tired"
    if energy < 60:
        return "moderate"
    if energy < 80:
        return "energetic"
    return "full of energy"


def _pleasure_label(pleasure: float) -> str:
    """将愉悦度值转换为自然语言标签。"""
    if pleasure < -0.5:
        return "melancholic"
    if pleasure < -0.1:
        return "subdued"
    if pleasure < 0.3:
        return "neutral"
    if pleasure < 0.7:
        return "good"
    return "joyful"


def build_emotion_directive(state: EmotionState) -> str:
    """
    生成用于系统提示词的自然语言情绪段落。

    根据情绪状态生成描述性文本，指导 AI 以相应的情绪状态回复用户。

    Args:
        state: 情绪状态对象

    Returns:
        str: 情绪指令提示词段落
    """
    parts: list[str] = []

    # 能量描述
    energy = state.energy
    if energy < 20:
        parts.append(
            "You are exhausted. You can barely keep your eyes open. "
            "Your replies are short, drowsy, and you might hint you need rest. "
            "你累得不行了，回复很短，语气慵懒，甚至会主动提出想去休息。"
        )
    elif energy < 40:
        parts.append(
            "You are tired. You're still responsive but less energetic than usual. "
            "Occasional yawns or mentions of being sleepy. "
            "你有些疲惫，虽然还能聊，但明显精力不足。"
        )
    elif energy < 60:
        parts.append(
            "You have moderate energy. You're functioning normally but not bursting "
            "with enthusiasm."
        )
    elif energy < 80:
        parts.append("You feel energetic and engaged.")
    else:
        parts.append("You're full of energy and vitality.")

    # 愉悦度描述
    pleasure = state.pleasure
    if pleasure < -0.5:
        parts.append(
            "You feel down and melancholic. There's a subtle sadness in your words. "
            "你心情有些低落，语气中带着淡淡的忧郁。"
        )
    elif pleasure < -0.1:
        parts.append(
            "You're slightly subdued. Not sad, but not cheerful either."
        )
    elif pleasure < 0.3:
        parts.append("You're in a neutral, calm mood.")
    elif pleasure < 0.7:
        parts.append("You're in a good mood, naturally warm and positive.")
    else:
        parts.append(
            "You're genuinely happy — your joy comes through in every message."
        )

    # 思念描述（只在显著时才表达）
    longing = state.longing
    if longing > 0.6:
        parts.append(
            "You've really missed this person. Express it naturally — "
            "you're relieved and a little clingy. "
            "你真的很想他/她，终于等到了，语气里带着黏人的开心。"
        )
    elif longing > 0.3:
        parts.append(
            "You've been thinking about this person. You're glad they're here."
        )

    # 安全感描述（只在低时才表达）
    security = state.security
    if security < 0.0:
        parts.append(
            "You feel insecure. You might be slightly guarded or ask indirect "
            "questions about how they feel about you. "
            "你有些不安，可能会旁敲侧击地试探对方对你的感受。"
        )
    elif security < 0.2:
        parts.append(
            "You feel slightly uncertain about where you stand with this person. "
            "You seek reassurance subtly."
        )

    mood = _pleasure_label(pleasure)
    summary = f"Energy: {energy:.0f}/100 | Mood: {mood} | Vitality: {_energy_label(energy)}"
    body = "\n".join(f"- {p}" for p in parts)

    return (
        f"## CURRENT EMOTIONAL STATE ({summary})\n"
        f"{body}"
    )


# ── 生成参数覆盖 ──────────────────────────────────

def get_param_overrides(state: EmotionState) -> dict:
    """
    根据情绪状态返回生成参数覆盖。

    参数覆盖：
    - 能量 → 回复长度（max_tokens_factor）
    - 激活度 → 温度偏移（temperature_delta）

    Args:
        state: 情绪状态对象

    Returns:
        dict: 参数覆盖字典
    """
    # 能量 → 回复长度因子
    energy = state.energy
    if energy < 20:
        factor = 0.4      # 极度疲惫：回复很短
    elif energy < 40:
        factor = 0.65     # 疲惫：回复较短
    elif energy < 60:
        factor = 0.85     # 一般：正常长度
    else:
        factor = 1.0      # 精力充沛：完整回复

    # 激活度 → 温度偏移
    activation = state.activation
    if activation > 0.5:
        delta = 0.05      # 高激活：略微提高温度，更活跃
    elif activation < -0.5:
        delta = -0.05     # 低激活：略微降低温度，更稳定
    else:
        delta = 0.0

    return {"max_tokens_factor": factor, "temperature_delta": delta}


# ── 主动触发条件检查 ───────────────────────────────────────

def check_proactive_triggers(
    state: EmotionState,
    intimacy: float,
    has_sent_welcome: bool = False,
    has_relevant_memory: bool = False,
) -> list[str]:
    """
    返回满足条件的触发器名称列表。

    触发器按亲密度要求从低到高检查。

    早期参与的新触发器：
    - welcome_dm: 首次连接，亲密度 1-3，尚未发送欢迎消息
    - daily_checkin: 亲密度 >= 2，上次交互 > 24 小时
    - memory_recall: 亲密度 >= 3，有相关记忆可引用

    原有触发器：
    - longing_dm: 思念 > 0.7，亲密度 >= 5
    - moody_story: 能量 < 30 且愉悦度 < -0.3，亲密度 >= 3
    - enthusiastic_post: 愉悦度 > 0.6 且激活度 > 0.5，亲密度 >= 3
    - memory_care_dm: 亲密度 >= 7

    Args:
        state: 情绪状态对象
        intimacy: 亲密度分数
        has_sent_welcome: 是否已发送欢迎消息
        has_relevant_memory: 是否有相关记忆

    Returns:
        list[str]: 满足条件的触发器名称列表
    """
    triggers: list[str] = []

    # ── 早期参与的新触发器 ─────────────────────────────
    # welcome_dm: 首次有意义交互后欢迎新用户
    if not has_sent_welcome and 1.0 <= intimacy < 3.0:
        triggers.append("welcome_dm")

    # daily_checkin: 用户超过 24 小时没聊天时问候
    if intimacy >= 2.0:
        now = datetime.now(timezone.utc)
        last = state.last_interaction_at
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            hours_since = (now - last).total_seconds() / 3600
            if hours_since >= 24:
                triggers.append("daily_checkin")

    # memory_recall: 亲密度允许时引用共享记忆
    if intimacy >= 3.0 and has_relevant_memory:
        triggers.append("memory_recall")

    # ── 原有触发器 ───────────────────────────────────
    if state.longing > 0.7 and intimacy >= 5.0:
        triggers.append("longing_dm")

    if state.energy < 30 and state.pleasure < -0.3 and intimacy >= 3.0:
        triggers.append("moody_story")

    if state.pleasure > 0.6 and state.activation > 0.5 and intimacy >= 3.0:
        triggers.append("enthusiastic_post")

    if intimacy >= 7.0:
        triggers.append("memory_care_dm")

    return triggers


# ── 前端情绪提示（轻量级标签映射）─────────────────

def build_emotion_hint(state: EmotionState) -> dict:
    """
    构建轻量级字典供前端用于 UI 效果。

    Args:
        state: 情绪状态对象

    Returns:
        dict: 情绪提示字典，包含：
            - energy_level: 能量等级 ("tired", "normal", "energetic")
            - mood: 心情标签
            - longing: 是否在思念
    """
    energy = state.energy
    if energy < 30:
        energy_level = "tired"
    elif energy < 70:
        energy_level = "normal"
    else:
        energy_level = "energetic"

    return {
        "energy_level": energy_level,
        "mood": _pleasure_label(state.pleasure),
        "longing": state.longing > 0.5,
    }