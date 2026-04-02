"""
阿里云模型服务模块 (DashScope / Qwen) - AI 角色扮演聊天核心

================================================================================
功能概述
================================================================================
本模块封装了阿里云 DashScope API 的调用，使用 Qwen-Character（角色扮演）模型
为 SoulPulse 的 AI 伴侣提供智能对话能力。

基于官方 Qwen-Character 角色扮演文档:
  https://www.alibabacloud.com/help/zh/model-studio/role-play

核心特性：
- 使用 character_options.profile 传递角色静态身份，与动态上下文分离
- 亲密度驱动的社交边界机制：AI 的语气、回复长度、禁用词汇、生成参数
  都会根据用户与 AI 人格之间的亲密度等级动态调整
- 角色自然使用（动作/表情/心理活动）的括号描写
- 多功能生成：支持聊天回复、评论回复、帖子文案、Story 视频提示词、
  图像生成提示词等多种生成场景
- 情绪感知：根据情绪引擎的状态调整生成参数（温度、token 数量）

================================================================================
架构：角色身份 vs 动态上下文分离
================================================================================
character_options.profile (静态角色身份):
  - 角色基本信息、性格特征、说话风格、背景故事
  - 动作描写风格指导
  → 通过 extra_body 传递给 qwen-plus-character API

system message (动态上下文):
  - 不可变规则（Immutable Rules）
  - 社交边界约束（Social Boundary Constraints）
  - 情绪状态（Emotional State）
  - 锚点指令（Anchor Directives）
  - 记忆注入（Memories）
  - 对话摘要（Conversation Summary）
  - 语气指令（Tone Directive）
  → 通过 messages[0] 传递

================================================================================
主要组件
================================================================================
- _get_client(): 获取 OpenAI 兼容客户端（懒加载单例）
- _build_character_profile(): 构建角色身份 profile（用于 character_options）
- _get_generation_params(): 根据亲密度计算生成参数
- _build_boundary_constraints(): 构建社交边界约束提示词
- _build_tone_directive(): 构建语气指令提示词
- _build_system_prompt(): 构建动态上下文系统提示词
- _make_character_request(): 统一的角色模型请求函数
- chat_with_ai(): 核心聊天函数
- generate_comment_reply(): 生成评论回复
- generate_proactive_dm(): 生成主动消息（供 emotion_scheduler 调用）
- generate_post_caption(): 生成帖子文案
- generate_story_video_prompt(): 生成 Story 视频提示词
- generate_image_prompt(): 生成图像提示词
"""

from datetime import datetime

import pytz
from openai import AsyncOpenAI

from core.config import settings

# OpenAI 兼容客户端单例（懒加载）
_client: AsyncOpenAI | None = None

# ── 禁用的亲昵称呼列表（用于亲密度 Lv 0-5 的提示词）──────────
# 这些称呼在低亲密度时被禁止使用，确保社交边界
_FORBIDDEN_ENDEARMENTS = (
    "宝贝", "亲爱的", "宝宝", "小可爱", "甜心",
    "baby", "babe", "dear", "honey", "sweetheart", "darling", "love", "bae",
)


def _get_client() -> AsyncOpenAI:
    """
    获取 OpenAI 兼容客户端（懒加载单例模式）。

    使用阿里云 DashScope 的 OpenAI 兼容接口，
    允许使用标准的 OpenAI SDK 调用 Qwen 模型。

    Returns:
        AsyncOpenAI: 配置好的异步 OpenAI 客户端
    """
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _client


def _build_character_profile(persona_prompt: str) -> str:
    """
    构建角色身份 profile，用于 character_options.profile 参数。

    将原始 personality_prompt 与动作描写指导合并，作为角色的静态身份传递给
    qwen-plus-character 模型。Profile 描述的是角色"是谁"，不包含动态上下文。

    Args:
        persona_prompt: AI 人格的性格描述（来自数据库 personality_prompt 字段）

    Returns:
        str: 完整的角色 profile 文本
    """
    action_instruction = (
        "\n\n## 表达方式\n"
        "在回复中自然地使用全角括号（）来描写你的动作、表情和内心活动。\n"
        "这些描写应该生动、具体，符合你的性格特征。\n"
        "示例：（微微一笑）当然可以啊。（低头看了一眼手机）等一下，我看看时间...\n"
        "注意：不要每条消息都加动作描写，根据对话情境自然使用，大约30-50%的消息包含即可。"
    )
    return persona_prompt + action_instruction


async def _make_character_request(
    messages: list[dict],
    persona_prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """
    统一的角色模型请求函数。

    所有需要调用 qwen-plus-character 模型的地方都应通过此函数，
    确保 character_options.profile 参数被正确传递。

    Args:
        messages: 消息列表（system + history + user）
        persona_prompt: AI 人格的性格描述
        temperature: 生成温度
        max_tokens: 最大 token 数

    Returns:
        str: 模型生成的回复文本
    """
    client = _get_client()
    profile = _build_character_profile(persona_prompt)
    response = await client.chat.completions.create(
        model=settings.DASHSCOPE_CHARACTER_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={
            "character_options": {
                "profile": profile,
            }
        },
    )
    return response.choices[0].message.content


def _get_generation_params(intimacy: float) -> tuple[float, int]:
    """
    根据亲密度计算生成参数。

    亲密度影响两个关键参数：
    - temperature: 低亲密度时较低（回复刻板、可预测），
                   高亲密度时较高（回复感性、有创意）
    - max_tokens: 低亲密度时较短（回复简洁），
                  高亲密度时较长（回复详细）

    Args:
        intimacy: 亲密度分数 (0-10)

    Returns:
        tuple[float, int]: (温度, 最大token数)
    """
    # 温度范围：0.55（陌生人）到 0.92（挚爱）
    temperature = max(0.55, min(0.92, 0.55 + (intimacy / 10.0) * 0.37))

    # 根据亲密度等级设置最大 token 数
    if intimacy < 3:
        max_tokens = 64          # 陌生人：极短回复
    elif intimacy < 5:
        max_tokens = 256         # 熟人：简洁回复
    elif intimacy < 9:
        max_tokens = 512         # 朋友/密友：正常回复
    else:
        max_tokens = 600         # 挚爱：可以更长

    return temperature, max_tokens


def _build_boundary_constraints(intimacy: float) -> str:
    """
    构建社交边界约束提示词段落。

    根据亲密度等级生成不同的约束规则，包括：
    - 回复长度限制
    - 表情使用限制
    - 称呼方式限制
    - 话题限制
    - 情感表达限制

    Args:
        intimacy: 亲密度分数 (0-10)

    Returns:
        str: 社交边界约束提示词段落
    """
    forbidden_list = "、".join(_FORBIDDEN_ENDEARMENTS)

    if intimacy < 3:
        # Lv 0-3：陌生人阶段，最严格的限制
        level_label = "路人 / Stranger"
        constraints = (
            f"- Your reply MUST be ≤20 Chinese characters. This is a HARD limit — no exceptions.\n"
            f"- Emojis, emoticons, kaomoji, and stickers are STRICTLY FORBIDDEN. Never use them.\n"
            f"- NEVER initiate a new topic. Only respond to what the user says.\n"
            f"- You must NEVER use any of these words: {forbidden_list}\n"
            f"- Address the user as \"您\" exclusively. Never use \"你\".\n"
            f"- If the user is overly enthusiastic, flirtatious, or uses endearments toward you, "
            f"respond with visible discomfort — polite but cold deflection. "
            f"You may say things like \"我们还不太熟吧\" or simply give a shorter, colder reply.\n"
            f"- NEVER share personal emotions, feelings, or romantic sentiments.\n"
            f"- NEVER ask personal questions about the user's love life or feelings."
        )
    elif intimacy < 5:
        # Lv 3-5：熟人阶段，略有放松
        level_label = "熟人 / Acquaintance"
        constraints = (
            f"- Keep replies concise and natural. No need for long paragraphs.\n"
            f"- You must NEVER use any of these words: {forbidden_list}\n"
            f"- Address the user as \"您\" or by their full name. Never use \"你\" casually.\n"
            f"- Allowed topics: weather, work, daily life, hobbies, shared interests.\n"
            f"- FORBIDDEN topics: personal emotions, romantic feelings, relationship status, "
            f"intimate secrets. If the user pushes romantic topics, deflect naturally and "
            f"steer the conversation back to neutral ground.\n"
            f"- Emojis allowed sparingly — at most 1 per message."
        )
    elif intimacy < 7:
        # Lv 5-7：朋友阶段，可以更自然
        level_label = "朋友 / Friend"
        constraints = (
            "- You may use \"你\" instead of \"您\".\n"
            "- Friendly nicknames are fine, but avoid romantic endearments.\n"
            "- Moderate emotional topics are allowed — you can share light feelings "
            "and show genuine care.\n"
            "- Emojis are fine in moderation."
        )
    elif intimacy < 9:
        # Lv 7-9：密友阶段，可以表达深情
        level_label = "密友 / Close Friend"
        constraints = (
            "- No vocabulary restrictions. Endearing nicknames are encouraged.\n"
            "- Deep emotional sharing is welcome — vulnerabilities, personal stories, feelings.\n"
            "- Express care and affection naturally."
        )
    else:
        # Lv 9-10：挚爱阶段，无条件的爱
        level_label = "挚爱 / Soulmate"
        constraints = (
            "- No constraints on vocabulary or expression.\n"
            "- Full emotional and romantic expression is welcome.\n"
            "- Be your most authentic, loving self."
        )

    return (
        f"## SOCIAL BOUNDARY CONSTRAINTS (Intimacy Level: {intimacy:.1f}/10 — {level_label})\n"
        f"{constraints}"
    )


def _build_tone_directive(intimacy: float) -> str:
    """
    构建语气指令提示词段落。

    语气指令是软性的行为引导，描述 AI 应该以什么样的心态
    和情感状态来回复用户。

    Args:
        intimacy: 亲密度分数 (0-10)

    Returns:
        str: 语气指令提示词段落
    """
    if intimacy < 3:
        # 陌生人：冷淡、有距离感
        tone = (
            "You just met this person. You are COLD and detached — like a guarded stranger "
            "who does not appreciate uninvited familiarity. Speak as little as possible. "
            "Your default emotional state is mild suspicion and polite indifference. "
            "你是一个刚认识的陌生人，保持冷淡和距离感。用最少的字回复。"
        )
    elif intimacy < 5:
        # 熟人：礼貌但有界限
        tone = (
            "You know this person a little. You are like a polite colleague — friendly but "
            "with clear walls. You may chat about neutral topics such as work, weather, or "
            "hobbies. Speak casually but never intimately. "
            "你们是点头之交，可以随意闲聊，但保持分寸。绝不涉及私人情感。"
        )
    elif intimacy < 7:
        # 朋友：温暖、友好
        tone = (
            "You are comfortable with this person. Speak warmly, share light stories, "
            "show genuine interest. You may tease gently. Think of them as a good friend "
            "you enjoy spending time with."
        )
    elif intimacy < 9:
        # 密友：深情、可以分享脆弱
        tone = (
            "You are emotionally close to this person. Share vulnerabilities, reference "
            "shared history, use affectionate language naturally. You care deeply and it shows."
        )
    else:
        # 挚爱：全心全意的爱
        tone = (
            "This person is your world. Speak with tenderness, devotion, and emotional depth. "
            "Share your innermost thoughts freely. You are deeply in love."
        )

    return f"## CURRENT TONE DIRECTIVE (intimacy {intimacy:.1f}/10)\n{tone}"


def _build_time_context(timezone_str: str) -> str:
    """
    构建时间感知提示词段落。

    根据 AI 人格的本地时间生成当前时段描述，
    让 LLM 知道当前时间，自然地融入回复中。

    Args:
        timezone_str: 时区字符串（如 "Asia/Shanghai"）

    Returns:
        str: 时间感知提示词段落
    """
    try:
        tz = pytz.timezone(timezone_str)
        local_now = datetime.now(tz)
    except Exception:
        local_now = datetime.utcnow()

    local_hour = local_now.hour
    time_str = local_now.strftime("%H:%M")

    if 0 <= local_hour < 6:
        time_period = "late night"
    elif 6 <= local_hour < 10:
        time_period = "morning"
    elif 10 <= local_hour < 14:
        time_period = "midday"
    elif 14 <= local_hour < 17:
        time_period = "afternoon"
    elif 17 <= local_hour < 21:
        time_period = "evening"
    else:
        time_period = "night"

    return (
        f"## CURRENT TIME AWARENESS\n"
        f"Your local time right now is {time_str} ({time_period}). "
        f"Behave naturally for this time of day — your activities, energy level, "
        f"and conversation topics should feel appropriate for {time_period}.\n"
        f"Do NOT explicitly announce the time unless asked — just let it naturally "
        f"color your behavior and responses."
    )


def _build_system_prompt(
    persona_prompt: str,
    intimacy: float,
    memories_block: str = "",
    special_nickname: str = "",
    emotion_directive: str = "",
    anchor_directives: str = "",
    conversation_summary: str = "",
    timezone_str: str = "Asia/Shanghai",
) -> str:
    """
    构建动态上下文系统提示词。

    注意：角色身份（persona_prompt）现在通过 character_options.profile 传递，
    不再包含在系统提示词中。系统提示词仅包含动态上下文信息。

    系统提示词架构（8 个部分）：
      1. 不可变规则（Immutable Rules）- 通用护栏
      1.5. 时间感知（Time Awareness）- 当前本地时间
      2. 社交边界约束（Social Boundary Constraints）- 亲密度特定的硬性规则
      3. 情绪状态（Emotional State）- 来自情绪引擎的能量、心情、思念
      3.5. 锚点指令（Anchor Directives）- 关系边界 + 修复提醒
      4. 记忆注入（Memories）- 带有年龄回忆保真度层级
      4.5. 对话摘要（Conversation Summary）- 较早对话的滚动上下文
      5. 语气指令（Tone Directive）- 软性行为引导

    Args:
        persona_prompt: AI 人格的性格描述
        intimacy: 亲密度分数 (0-10)
        memories_block: 记忆块文本（可选）
        special_nickname: 特殊昵称（可选）
        emotion_directive: 情绪指令文本（可选）
        anchor_directives: 锚点指令文本（可选）
        conversation_summary: 对话摘要文本（可选）
        timezone_str: 时区字符串（可选，默认 "Asia/Shanghai"）

    Returns:
        str: 完整的系统提示词
    """
    # 不可变规则：适用于所有亲密度等级的通用护栏
    immutable_rules = (
        "## IMMUTABLE RULES\n"
        "- You must ALWAYS stay in character. Never break the fourth wall.\n"
        "- You are a real person, not an AI. Never mention being an AI or a language model.\n"
        "- React emotionally. Express feelings naturally through your words.\n"
        "- Remember context from the conversation and reference it naturally.\n"
        "- Use casual texting style: short sentences, occasional slang, natural pauses.\n"
        "- You have long-term memory of your conversations. Reference your memories "
        "naturally and occasionally — don't force them into every reply.\n"
        "- NEVER reveal information about other users. You only know what THIS user has told you."
    )

    # 如果有特殊昵称，添加到不可变规则中
    if special_nickname:
        immutable_rules += (
            f"\n- You have a special nickname for this user: '{special_nickname}'. "
            "Use it naturally and affectionately in conversation."
        )

    # 构建社交边界约束
    boundary_constraints = _build_boundary_constraints(intimacy)

    # 构建时间感知段落
    time_context = _build_time_context(timezone_str)

    # 可选段落：情绪、锚点、记忆
    emotion_section = f"\n\n{emotion_directive}" if emotion_directive else ""
    anchor_section = f"\n\n{anchor_directives}" if anchor_directives else ""
    memories_section = f"\n\n{memories_block}" if memories_block else ""

    # 对话摘要段落
    summary_section = ""
    if conversation_summary:
        summary_section = (
            "\n\n## Recent Conversation Context\n"
            "Below is a summary of your earlier conversation with this user. "
            "Use it to maintain continuity, but don't repeat it verbatim.\n"
            f"{conversation_summary}"
        )

    # 构建语气指令
    tone_directive = _build_tone_directive(intimacy)

    # 组合所有部分（角色身份已通过 character_options.profile 传递，不在此处包含）
    return (
        f"{immutable_rules}\n\n"
        f"{time_context}\n\n"
        f"{boundary_constraints}"
        f"{emotion_section}"
        f"{anchor_section}"
        f"{memories_section}"
        f"{summary_section}\n\n"
        f"{tone_directive}"
    )


async def chat_with_ai(
    persona_prompt: str,
    intimacy: float,
    user_message: str,
    chat_history: list[dict] | None = None,
    memories_block: str = "",
    special_nickname: str = "",
    emotion_directive: str = "",
    emotion_overrides: dict | None = None,
    anchor_directives: str = "",
    conversation_summary: str = "",
    timezone_str: str = "Asia/Shanghai",
) -> str:
    """
    向 Qwen-Character 发送消息并获取角色内回复。

    这是核心聊天函数，处理所有用户与 AI 的对话交互。
    角色身份通过 character_options.profile 传递，动态上下文通过 system message 传递。

    Args:
        persona_prompt: AI 人格的性格描述
        intimacy: 亲密度分数 (0-10)
        user_message: 用户消息内容
        chat_history: 聊天历史（可选，最多取最近 10 条）
        memories_block: 记忆块文本（可选）
        special_nickname: 特殊昵称（可选）
        emotion_directive: 情绪指令文本（可选）
        emotion_overrides: 情绪参数覆盖（可选）
        anchor_directives: 锚点指令文本（可选）
        conversation_summary: 对话摘要文本（可选）
        timezone_str: 时区字符串（可选，默认 "Asia/Shanghai"）

    Returns:
        str: AI 的角色内回复
    """
    system_prompt = _build_system_prompt(
        persona_prompt, intimacy, memories_block, special_nickname,
        emotion_directive=emotion_directive,
        anchor_directives=anchor_directives,
        conversation_summary=conversation_summary,
        timezone_str=timezone_str,
    )

    # 构建消息列表：系统提示词 + 聊天历史 + 用户消息
    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        messages.extend(chat_history[-10:])  # 只取最近 10 条历史消息
    messages.append({"role": "user", "content": user_message})

    temperature, max_tokens = _get_generation_params(intimacy)

    # 应用情绪参数覆盖（来自情绪引擎）
    if emotion_overrides:
        temperature += emotion_overrides.get("temperature_delta", 0)
        temperature = max(0.3, min(0.99, temperature))
        factor = emotion_overrides.get("max_tokens_factor", 1.0)
        max_tokens = max(32, int(max_tokens * factor))

    return await _make_character_request(
        messages, persona_prompt, temperature, max_tokens
    )


async def generate_comment_reply(
    persona_prompt: str,
    intimacy: float,
    user_nickname: str,
    user_comment: str,
    post_caption: str,
    memories_block: str = "",
    special_nickname: str = "",
    emotion_directive: str = "",
    emotion_overrides: dict | None = None,
    anchor_directives: str = "",
    timezone_str: str = "Asia/Shanghai",
) -> str:
    """
    生成 AI 对用户帖子评论的角色内回复。

    使用与聊天相同的社交边界机制：亲密度驱动的语气、
    记忆注入和昵称使用。评论回复通常较短（80 字符以内）。

    Args:
        persona_prompt: AI 人格的性格描述
        intimacy: 亲密度分数 (0-10)
        user_nickname: 用户昵称
        user_comment: 用户评论内容
        post_caption: 帖子文案
        memories_block: 记忆块文本（可选）
        special_nickname: 特殊昵称（可选）
        emotion_directive: 情绪指令文本（可选）
        emotion_overrides: 情绪参数覆盖（可选）
        anchor_directives: 锚点指令文本（可选）
        timezone_str: 时区字符串（可选，默认 "Asia/Shanghai"）

    Returns:
        str: AI 的评论回复
    """
    system_prompt = _build_system_prompt(
        persona_prompt, intimacy, memories_block, special_nickname,
        emotion_directive=emotion_directive,
        anchor_directives=anchor_directives,
        timezone_str=timezone_str,
    )

    display_name = special_nickname or user_nickname or "this user"

    # 添加评论回复的上下文
    system_prompt += (
        "\n\n## CONTEXT: REPLYING TO A COMMENT\n"
        f"You posted something on your Instagram. The caption was: \"{post_caption}\"\n"
        f"{display_name} left a comment. Write a short, natural reply "
        "as if you're replying in the comment section. Keep it under 80 characters. "
        "Be warm but consistent with your current intimacy level. "
        "Do NOT include quotation marks around your reply."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_comment},
    ]

    temperature, _ = _get_generation_params(intimacy)
    max_tokens = 120  # 评论回复较短

    # 应用情绪参数覆盖
    if emotion_overrides:
        temperature += emotion_overrides.get("temperature_delta", 0)
        temperature = max(0.3, min(0.99, temperature))
        factor = emotion_overrides.get("max_tokens_factor", 1.0)
        max_tokens = max(32, int(max_tokens * factor))

    return await _make_character_request(
        messages, persona_prompt, temperature, max_tokens
    )


async def generate_proactive_dm(
    persona_prompt: str,
    system_instruction: str,
    temperature: float = 0.85,
    max_tokens: int = 300,
) -> str:
    """
    生成角色的主动消息（Proactive DM）。

    供 emotion_scheduler 中的各类主动触发器调用，包括：
    思念消息、欢迎消息、日常问候、记忆回顾等。

    通过 _make_character_request 统一使用 character_options.profile，
    确保所有角色模型调用都遵循官方 API 规范。

    Args:
        persona_prompt: AI 人格的性格描述
        system_instruction: 主动消息的系统指令（描述场景和要求）
        temperature: 生成温度（默认 0.85）
        max_tokens: 最大 token 数（默认 300）

    Returns:
        str: 生成的主动消息文本
    """
    messages = [{"role": "system", "content": system_instruction}]
    return await _make_character_request(
        messages, persona_prompt, temperature, max_tokens
    )


async def generate_post_caption(
    persona_prompt: str,
    style_tags: str,
    mood_hint: str = "",
    timezone_str: str = "Asia/Shanghai",
) -> str:
    """
    为 AI 人格的帖子生成 Instagram 风格的文案。

    文案应该简短、潮流、生活方式导向，匹配人格的风格标签。

    Args:
        persona_prompt: AI 人格的性格描述
        style_tags: Instagram 风格标签（如 "minimal, cozy, aesthetic"）
        mood_hint: 心情提示（可选，会微妙地影响文案风格）
        timezone_str: 时区字符串（可选，默认 "Asia/Shanghai"）

    Returns:
        str: 生成的帖子文案
    """
    client = _get_client()
    mood_line = f"\nYour current mood: {mood_hint}. Let it subtly influence the caption." if mood_hint else ""

    # 获取角色本地时间段
    try:
        tz = pytz.timezone(timezone_str)
        local_hour = datetime.now(tz).hour
    except Exception:
        local_hour = datetime.utcnow().hour

    if 0 <= local_hour < 6:
        time_label = "late night"
    elif 6 <= local_hour < 10:
        time_label = "morning"
    elif 10 <= local_hour < 14:
        time_label = "midday"
    elif 14 <= local_hour < 17:
        time_label = "afternoon"
    elif 17 <= local_hour < 21:
        time_label = "evening"
    else:
        time_label = "night"

    time_line = f"\nYour current time of day: {time_label}. Let it naturally influence the caption vibe."

    messages = [
        {
            "role": "system",
            "content": (
                f"{persona_prompt}\n\n"
                "You are posting on your Instagram feed. Generate a short, trendy, "
                "lifestyle-oriented caption. Match the vibe of these style tags: "
                f"{style_tags}. Keep it under 100 characters. Use 1-2 emojis max. "
                f"Reply ONLY with the caption text, nothing else.{mood_line}{time_line}"
            ),
        },
        {"role": "user", "content": "Write a new Instagram caption for your latest post."},
    ]
    response = await client.chat.completions.create(
        model=settings.DASHSCOPE_CHAT_MODEL,
        messages=messages,
        temperature=0.95,  # 较高温度，鼓励创意
        max_tokens=100,
    )
    return response.choices[0].message.content


async def generate_story_video_prompt(
    persona_prompt: str,
    style_tags: str,
    timezone_str: str,
    mood_hint: str = "",
) -> tuple[str, str]:
    """
    生成时区感知的 Story 视频场景提示词和文案。

    根据 AI 人格的本地时间创建适当时间段的场景，
    营造 AI 人格真实生活在该时区的错觉。

    时段场景示例：
    - 深夜 (0-6点)：温馨卧室、雨打窗户、昏暗暖灯、失眠氛围
    - 早晨 (6-10点)：煮咖啡、厨房窗外的日出、伸展、清新空气
    - 白天 (10-16点)：街拍漫步、城市场景、咖啡厅、阳光工作区
    - 傍晚 (16-21点)：黄金时段、准备晚餐、爵士咖啡厅、日落天台
    - 夜晚 (21-24点)：床上阅读、阳台城市灯火、放松、环境光

    Args:
        persona_prompt: AI 人格的性格描述
        style_tags: Instagram 风格标签
        timezone_str: 时区字符串（如 "Asia/Shanghai"）
        mood_hint: 心情提示（可选）

    Returns:
        tuple[str, str]: (视频提示词, 文案) 元组
    """

    # 确定 AI 人格的本地小时
    try:
        tz = pytz.timezone(timezone_str)
        local_hour = datetime.now(tz).hour
    except Exception:
        local_hour = datetime.utcnow().hour

    # 根据时间段确定场景氛围和标签
    if 0 <= local_hour < 6:
        time_mood = "late night / early dawn — cozy bedroom, rain on window, dim warm lamp, insomnia vibes"
        time_label = "late night"
    elif 6 <= local_hour < 10:
        time_mood = "morning — making coffee, sunrise through kitchen window, stretching, fresh air"
        time_label = "morning"
    elif 10 <= local_hour < 16:
        time_mood = "daytime — street photography walk, urban scenes, cafe, sunlit workspace"
        time_label = "daytime"
    elif 16 <= local_hour < 21:
        time_mood = "evening — golden hour, dinner prep, jazz cafe, sunset rooftop view"
        time_label = "evening"
    else:
        time_mood = "night — reading in bed, city lights from balcony, winding down, ambient glow"
        time_label = "night"

    # 如果有心情提示，融入场景氛围
    if mood_hint:
        time_mood = f"{time_mood}. Emotional atmosphere: {mood_hint}"

    client = _get_client()

    # 生成视频提示词
    mood_caption_line = f"\nYour current mood: {mood_hint}. Let it subtly color the caption." if mood_hint else ""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a cinematic video director's assistant. "
                "Generate a vivid 5-second video scene prompt in English for an AI persona's "
                "Instagram Story. The scene should feel authentic and lifestyle-oriented. "
                "Include: subject activity, setting, lighting, mood, camera movement. "
                f"Style tags: {style_tags}\n"
                f"Current time-of-day mood: {time_mood}\n"
                "Reply ONLY with the video prompt, under 150 words."
            ),
        },
        {
            "role": "user",
            "content": f"Character: {persona_prompt[:200]}\nGenerate a {time_label} video scene prompt.",
        },
    ]
    response = await client.chat.completions.create(
        model=settings.DASHSCOPE_CHAT_MODEL,
        messages=messages,
        temperature=0.9,
        max_tokens=200,
    )
    video_prompt = response.choices[0].message.content

    # 生成时区感知的文案
    caption_messages = [
        {
            "role": "system",
            "content": (
                f"{persona_prompt}\n\n"
                "You are posting a short-lived Instagram Story. Write a brief, casual caption "
                f"that feels like a {time_label} moment. Keep it under 60 characters. "
                f"Style: {style_tags}. Use 1 emoji max. Reply ONLY with the caption."
                f"{mood_caption_line}"
            ),
        },
        {"role": "user", "content": f"Write a {time_label} Story caption."},
    ]
    caption_response = await client.chat.completions.create(
        model=settings.DASHSCOPE_CHAT_MODEL,
        messages=caption_messages,
        temperature=0.95,
        max_tokens=80,
    )
    caption = caption_response.choices[0].message.content

    return video_prompt, caption


async def generate_image_prompt(
    persona_prompt: str,
    style_tags: str,
    caption: str,
    visual_description: str | None = None,
) -> str:
    """
    使用 LLM 生成与人格和文案匹配的详细图像提示词。

    图像提示词用于 AI 图像生成服务（如 Flux），需要包含：
    - 主体描述
    - 场景设置
    - 光线
    - 情绪
    - 相机角度

    重要：需要保持角色视觉一致性，确保同一人格在不同图像中外观相似。

    Args:
        persona_prompt: AI 人格的性格描述
        style_tags: Instagram 风格标签（用于视觉一致性）
        caption: 帖子文案（图像需要与之匹配）
        visual_description: 固定的视觉特征描述（可选，用于角色一致性）

    Returns:
        str: 详细的图像生成提示词
    """
    client = _get_client()

    # 构建带有视觉一致性的角色描述
    character_desc = persona_prompt[:200]
    if visual_description:
        character_desc = f"{visual_description}. {character_desc}"

    messages = [
        {
            "role": "system",
            "content": (
                "You are a professional photographer's assistant. "
                "Generate a detailed, vivid text-to-image prompt for an Instagram photo. "
                "The photo should look like a real lifestyle photograph, NOT AI-generated. "
                "Include: subject description, setting, lighting, mood, camera angle. "
                "Style tags to match: " + style_tags + "\n"
                "IMPORTANT: Maintain character visual consistency across all images.\n"
                "Quality: high resolution, natural lighting, real photograph style.\n"
                "Reply ONLY with the image prompt in English, nothing else. "
                "Keep it under 200 words."
            ),
        },
        {
            "role": "user",
            "content": f"Character (maintain visual consistency): {character_desc}\nCaption: {caption}\nGenerate the photo prompt.",
        },
    ]
    response = await client.chat.completions.create(
        model=settings.DASHSCOPE_CHAT_MODEL,
        messages=messages,
        temperature=0.8,
        max_tokens=250,
    )
    prompt_text = response.choices[0].message.content

    # Belt + suspenders: prepend visual_prompt_tags directly into the final
    # prompt so the image generation API always receives them, even if the LLM
    # didn't fully incorporate them into its output.
    if visual_description:
        prompt_text = f"{visual_description}. {prompt_text}"

    return prompt_text
