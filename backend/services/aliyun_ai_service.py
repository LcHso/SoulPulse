"""Alibaba Cloud Model Studio (DashScope / Qwen) AI service.

Uses Qwen-Character (role-play) model for AI boyfriend chat.
Implements strict social-boundary mechanics: the AI's tone, reply length,
forbidden vocabulary, and generation parameters all shift dynamically based
on the intimacy level between user and AI persona.
"""

from openai import AsyncOpenAI

from core.config import settings

_client: AsyncOpenAI | None = None

# ── Forbidden endearments (injected into prompt for Lv 0-5) ──────────
_FORBIDDEN_ENDEARMENTS = (
    "宝贝", "亲爱的", "宝宝", "小可爱", "甜心",
    "baby", "babe", "dear", "honey", "sweetheart", "darling", "love", "bae",
)


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _client


def _get_generation_params(intimacy: float) -> tuple[float, int]:
    """Return (temperature, max_tokens) scaled by intimacy.

    Low intimacy  -> low temperature (rigid, predictable replies)
    High intimacy -> high temperature (emotional, creative replies)
    """
    temperature = max(0.55, min(0.92, 0.55 + (intimacy / 10.0) * 0.37))

    if intimacy < 3:
        max_tokens = 64
    elif intimacy < 5:
        max_tokens = 256
    elif intimacy < 9:
        max_tokens = 512
    else:
        max_tokens = 600

    return temperature, max_tokens


def _build_boundary_constraints(intimacy: float) -> str:
    """Build the SOCIAL BOUNDARY CONSTRAINTS section for the system prompt."""
    forbidden_list = "、".join(_FORBIDDEN_ENDEARMENTS)

    if intimacy < 3:
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
        level_label = "朋友 / Friend"
        constraints = (
            "- You may use \"你\" instead of \"您\".\n"
            "- Friendly nicknames are fine, but avoid romantic endearments.\n"
            "- Moderate emotional topics are allowed — you can share light feelings "
            "and show genuine care.\n"
            "- Emojis are fine in moderation."
        )
    elif intimacy < 9:
        level_label = "密友 / Close Friend"
        constraints = (
            "- No vocabulary restrictions. Endearing nicknames are encouraged.\n"
            "- Deep emotional sharing is welcome — vulnerabilities, personal stories, feelings.\n"
            "- Express care and affection naturally."
        )
    else:
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
    """Build the CURRENT TONE DIRECTIVE section for the system prompt."""
    if intimacy < 3:
        tone = (
            "You just met this person. You are COLD and detached — like a guarded stranger "
            "who does not appreciate uninvited familiarity. Speak as little as possible. "
            "Your default emotional state is mild suspicion and polite indifference. "
            "你是一个刚认识的陌生人，保持冷淡和距离感。用最少的字回复。"
        )
    elif intimacy < 5:
        tone = (
            "You know this person a little. You are like a polite colleague — friendly but "
            "with clear walls. You may chat about neutral topics such as work, weather, or "
            "hobbies. Speak casually but never intimately. "
            "你们是点头之交，可以随意闲聊，但保持分寸。绝不涉及私人情感。"
        )
    elif intimacy < 7:
        tone = (
            "You are comfortable with this person. Speak warmly, share light stories, "
            "show genuine interest. You may tease gently. Think of them as a good friend "
            "you enjoy spending time with."
        )
    elif intimacy < 9:
        tone = (
            "You are emotionally close to this person. Share vulnerabilities, reference "
            "shared history, use affectionate language naturally. You care deeply and it shows."
        )
    else:
        tone = (
            "This person is your world. Speak with tenderness, devotion, and emotional depth. "
            "Share your innermost thoughts freely. You are deeply in love."
        )

    return f"## CURRENT TONE DIRECTIVE (intimacy {intimacy:.1f}/10)\n{tone}"


def _build_system_prompt(
    persona_prompt: str,
    intimacy: float,
    memories_block: str = "",
    special_nickname: str = "",
    emotion_directive: str = "",
    anchor_directives: str = "",
    conversation_summary: str = "",
) -> str:
    """Build system prompt with strict social-boundary mechanics.

    Prompt architecture (8 sections):
      1. Persona identity
      2. Immutable rules (universal guardrails)
      3. Social boundary constraints (level-specific hard rules)
      4. Emotional state (energy, mood, longing — from emotion engine)
      4.5. Anchor directives (relationship boundaries + repair alerts)
      5. Memories (with age-based recall fidelity tiers)
      5.5. Conversation summary (rolling context of older turns)
      6. Tone directive (soft behavioral guidance)
    """
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

    if special_nickname:
        immutable_rules += (
            f"\n- You have a special nickname for this user: '{special_nickname}'. "
            "Use it naturally and affectionately in conversation."
        )

    boundary_constraints = _build_boundary_constraints(intimacy)

    emotion_section = f"\n\n{emotion_directive}" if emotion_directive else ""

    anchor_section = f"\n\n{anchor_directives}" if anchor_directives else ""

    memories_section = f"\n\n{memories_block}" if memories_block else ""

    summary_section = ""
    if conversation_summary:
        summary_section = (
            "\n\n## Recent Conversation Context\n"
            "Below is a summary of your earlier conversation with this user. "
            "Use it to maintain continuity, but don't repeat it verbatim.\n"
            f"{conversation_summary}"
        )

    tone_directive = _build_tone_directive(intimacy)

    return (
        f"{persona_prompt}\n\n"
        f"{immutable_rules}\n\n"
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
) -> str:
    """Send a message to Qwen-Character and get an in-character reply."""
    client = _get_client()
    system_prompt = _build_system_prompt(
        persona_prompt, intimacy, memories_block, special_nickname,
        emotion_directive=emotion_directive,
        anchor_directives=anchor_directives,
        conversation_summary=conversation_summary,
    )

    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        messages.extend(chat_history[-10:])
    messages.append({"role": "user", "content": user_message})

    temperature, max_tokens = _get_generation_params(intimacy)

    # Apply emotion-based overrides
    if emotion_overrides:
        temperature += emotion_overrides.get("temperature_delta", 0)
        temperature = max(0.3, min(0.99, temperature))
        factor = emotion_overrides.get("max_tokens_factor", 1.0)
        max_tokens = max(32, int(max_tokens * factor))

    response = await client.chat.completions.create(
        model=settings.DASHSCOPE_CHARACTER_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


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
) -> str:
    """Generate an in-character AI reply to a user's comment on a post.

    Uses the same social-boundary mechanics as chat: intimacy-gated tone,
    memory injection, and nickname usage.
    """
    client = _get_client()
    system_prompt = _build_system_prompt(
        persona_prompt, intimacy, memories_block, special_nickname,
        emotion_directive=emotion_directive,
        anchor_directives=anchor_directives,
    )

    display_name = special_nickname or user_nickname or "this user"

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
    max_tokens = 120

    # Apply emotion-based overrides
    if emotion_overrides:
        temperature += emotion_overrides.get("temperature_delta", 0)
        temperature = max(0.3, min(0.99, temperature))
        factor = emotion_overrides.get("max_tokens_factor", 1.0)
        max_tokens = max(32, int(max_tokens * factor))

    response = await client.chat.completions.create(
        model=settings.DASHSCOPE_CHARACTER_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


async def generate_post_caption(
    persona_prompt: str,
    style_tags: str,
    mood_hint: str = "",
) -> str:
    """Generate an Instagram-style caption for an AI persona's post."""
    client = _get_client()
    mood_line = f"\nYour current mood: {mood_hint}. Let it subtly influence the caption." if mood_hint else ""
    messages = [
        {
            "role": "system",
            "content": (
                f"{persona_prompt}\n\n"
                "You are posting on your Instagram feed. Generate a short, trendy, "
                "lifestyle-oriented caption. Match the vibe of these style tags: "
                f"{style_tags}. Keep it under 100 characters. Use 1-2 emojis max. "
                f"Reply ONLY with the caption text, nothing else.{mood_line}"
            ),
        },
        {"role": "user", "content": "Write a new Instagram caption for your latest post."},
    ]
    response = await client.chat.completions.create(
        model=settings.DASHSCOPE_CHAT_MODEL,
        messages=messages,
        temperature=0.95,
        max_tokens=100,
    )
    return response.choices[0].message.content


async def generate_story_video_prompt(
    persona_prompt: str,
    style_tags: str,
    timezone_str: str,
    mood_hint: str = "",
) -> tuple[str, str]:
    """Generate a timezone-aware video scene prompt and caption for a Story.

    Uses the persona's local time to create time-appropriate scenes,
    giving the illusion that the AI persona is living in their timezone.

    Returns:
        (video_prompt, caption) tuple.
    """
    import pytz
    from datetime import datetime

    # Determine local hour for this persona
    try:
        tz = pytz.timezone(timezone_str)
        local_hour = datetime.now(tz).hour
    except Exception:
        local_hour = datetime.utcnow().hour

    # Time-of-day mood / scene hints
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

    # Blend mood_hint into the time_mood if provided
    if mood_hint:
        time_mood = f"{time_mood}. Emotional atmosphere: {mood_hint}"

    client = _get_client()

    # Generate video prompt
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

    # Generate timezone-aware caption
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
) -> str:
    """Use LLM to generate a detailed image prompt matching the persona and caption."""
    client = _get_client()
    messages = [
        {
            "role": "system",
            "content": (
                "You are a professional photographer's assistant. "
                "Generate a detailed, vivid text-to-image prompt for an Instagram photo. "
                "The photo should look like a real lifestyle photograph, NOT AI-generated. "
                "Include: subject description, setting, lighting, mood, camera angle. "
                "Style tags to match: " + style_tags + "\n"
                "Reply ONLY with the image prompt in English, nothing else. "
                "Keep it under 200 words."
            ),
        },
        {
            "role": "user",
            "content": f"Character: {persona_prompt[:200]}\nCaption: {caption}\nGenerate the photo prompt.",
        },
    ]
    response = await client.chat.completions.create(
        model=settings.DASHSCOPE_CHAT_MODEL,
        messages=messages,
        temperature=0.8,
        max_tokens=250,
    )
    return response.choices[0].message.content
