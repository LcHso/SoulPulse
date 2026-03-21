"""Emotion State Machine — core engine.

Stateless functions that manage the physiology (energy) and psychology
(pleasure, activation, longing, security) of each user↔AI relationship.

Design principle:
  Intimacy = gate  (what the AI is *permitted* to do)
  Emotion  = driver (how the AI *chooses* to behave)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.emotion_state import EmotionState

logger = logging.getLogger(__name__)

# ── Default dimensions for new relationships ────────────────────────
DEFAULT_ENERGY = 80.0
DEFAULT_PLEASURE = 0.3
DEFAULT_ACTIVATION = 0.2
DEFAULT_LONGING = 0.0
DEFAULT_SECURITY = 0.5

# ── Caring-intent keyword lists (hot-path, no LLM) ─────────────────
_CARING_KEYWORDS_ZH = (
    "早睡", "晚安", "好好休息", "注意身体", "别太累", "照顾好自己",
    "心疼", "辛苦了", "早点睡", "多喝水", "保重", "别熬夜", "好好吃饭",
)
_CARING_KEYWORDS_EN = (
    "rest well", "good night", "take care", "don't overwork",
    "sleep well", "get some rest", "take it easy",
    "look after yourself", "don't stay up",
)

# Max hours for time-decay calculation (caps extreme swings after long absence)
_MAX_DECAY_HOURS = 168  # 1 week


# ── Clamping ────────────────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _clamp_state(s: EmotionState) -> EmotionState:
    s.energy = _clamp(s.energy, 0.0, 100.0)
    s.pleasure = _clamp(s.pleasure, -1.0, 1.0)
    s.activation = _clamp(s.activation, -1.0, 1.0)
    s.longing = _clamp(s.longing, 0.0, 1.0)
    s.security = _clamp(s.security, -1.0, 1.0)
    return s


# ── Core functions ──────────────────────────────────────────────────

async def get_or_create(
    db: AsyncSession, user_id: int, ai_id: int,
) -> EmotionState:
    """Load the emotion state for a user↔AI pair, applying time decay.

    Creates a fresh row with warm defaults if none exists.
    """
    result = await db.execute(
        select(EmotionState).where(
            EmotionState.user_id == user_id,
            EmotionState.ai_id == ai_id,
        )
    )
    state = result.scalar_one_or_none()

    if state is not None:
        apply_time_decay(state)
        return state

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
    """Apply passive time-based changes since last interaction.

    - Energy recovers (+5/h)
    - Pleasure & activation drift toward 0 (multiplicative)
    - Longing grows (+0.03/h)
    - Security drifts down slightly (-0.003/h)

    Caps elapsed time at 168 h (1 week).
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

    # Physiology: rest recovers energy
    state.energy += 5.0 * hours

    # Psychology: pleasure & activation decay multiplicatively toward 0
    state.pleasure *= 0.98 ** hours
    state.activation *= 0.95 ** hours

    # Longing grows with absence
    state.longing += 0.03 * hours

    # Security drifts down slightly
    state.security -= 0.003 * hours

    state.last_interaction_at = now
    return _clamp_state(state)


# ── Interaction effects ─────────────────────────────────────────────

# Effect matrix: (energy, pleasure, activation, longing_mode, longing_val, security)
# longing_mode: "mul" = multiply current longing, "add" = additive change
_EFFECTS: dict[str, dict] = {
    "chat": {
        "energy": -3, "pleasure": 0.05, "activation": 0.05,
        "longing_mode": "mul", "longing_val": 0.5, "security": 0.02,
    },
    "chat_long": {
        "energy": -5, "pleasure": 0.05, "activation": 0.03,
        "longing_mode": "mul", "longing_val": 0.3, "security": 0.02,
    },
    "chat_caring": {
        "energy": 12, "pleasure": 0.10, "activation": -0.05,
        "longing_mode": "mul", "longing_val": 0.2, "security": 0.08,
    },
    "comment": {
        "energy": -1, "pleasure": 0.03, "activation": 0.02,
        "longing_mode": "add", "longing_val": -0.05, "security": 0.02,
    },
    "like": {
        "energy": 0, "pleasure": 0.05, "activation": 0.01,
        "longing_mode": "add", "longing_val": -0.03, "security": 0.03,
    },
    "generate_post": {
        "energy": -8, "pleasure": 0, "activation": 0.02,
        "longing_mode": "add", "longing_val": 0, "security": 0,
    },
    "generate_story": {
        "energy": -10, "pleasure": 0, "activation": 0.03,
        "longing_mode": "add", "longing_val": 0, "security": 0,
    },
}


def apply_interaction(
    state: EmotionState,
    event: str,
    metadata: dict | None = None,
) -> EmotionState:
    """Update emotion dimensions based on an interaction event."""
    fx = _EFFECTS.get(event)
    if fx is None:
        logger.warning("Unknown emotion event: %s", event)
        return state

    state.energy += fx["energy"]
    state.pleasure += fx["pleasure"]
    state.activation += fx["activation"]
    state.security += fx["security"]

    if fx["longing_mode"] == "mul":
        state.longing *= fx["longing_val"]
    else:
        state.longing += fx["longing_val"]

    state.last_interaction_at = datetime.now(timezone.utc)
    return _clamp_state(state)


# ── Caring-intent detection (keyword, no LLM) ──────────────────────

def detect_caring_intent(message: str) -> bool:
    """Return True if the message contains caring/rest keywords."""
    lower = message.lower()
    for kw in _CARING_KEYWORDS_ZH:
        if kw in message:
            return True
    for kw in _CARING_KEYWORDS_EN:
        if kw in lower:
            return True
    return False


def classify_chat_event(message: str) -> str:
    """Classify a user chat message into an emotion event type."""
    if detect_caring_intent(message):
        return "chat_caring"
    if len(message) > 100:
        return "chat_long"
    return "chat"


# ── Prompt directive generation ─────────────────────────────────────

def _energy_label(energy: float) -> str:
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
    """Generate a natural-language emotion section for the system prompt."""
    parts: list[str] = []

    # Energy
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

    # Pleasure
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

    # Longing (only surface if notable)
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

    # Security (only surface if low)
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


# ── Generation parameter overrides ──────────────────────────────────

def get_param_overrides(state: EmotionState) -> dict:
    """Return temperature_delta and max_tokens_factor based on emotion."""
    # Energy → reply length
    energy = state.energy
    if energy < 20:
        factor = 0.4
    elif energy < 40:
        factor = 0.65
    elif energy < 60:
        factor = 0.85
    else:
        factor = 1.0

    # Activation → temperature shift
    activation = state.activation
    if activation > 0.5:
        delta = 0.05
    elif activation < -0.5:
        delta = -0.05
    else:
        delta = 0.0

    return {"max_tokens_factor": factor, "temperature_delta": delta}


# ── Proactive trigger checks ───────────────────────────────────────

def check_proactive_triggers(
    state: EmotionState, intimacy: float,
) -> list[str]:
    """Return a list of trigger names whose conditions are met."""
    triggers: list[str] = []

    if state.longing > 0.7 and intimacy >= 5.0:
        triggers.append("longing_dm")

    if state.energy < 30 and state.pleasure < -0.3 and intimacy >= 3.0:
        triggers.append("moody_story")

    if state.pleasure > 0.6 and state.activation > 0.5 and intimacy >= 3.0:
        triggers.append("enthusiastic_post")

    if intimacy >= 7.0:
        triggers.append("memory_care_dm")

    return triggers


# ── Emotion hint for frontend (cheap label mapping) ─────────────────

def build_emotion_hint(state: EmotionState) -> dict:
    """Build a lightweight dict the frontend can use for UI effects."""
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
