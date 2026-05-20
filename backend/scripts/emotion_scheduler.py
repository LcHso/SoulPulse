"""
情绪驱动调度器 - SoulPulse 主动行为核心模块

功能概述：
    该模块是 SoulPulse AI 伴侣系统的核心调度器，负责根据 AI 的情绪状态
    自动触发各种主动行为，使 AI 能够主动与用户互动，增强情感连接。

调度逻辑：
    每 30 分钟运行一次扫描循环（CHECK_INTERVAL = 1800秒），对所有活跃的
    情绪状态（EmotionState）进行处理：
      1. 应用被动时间衰减（能量恢复、思念增长等）
      2. 检查主动行为触发条件
      3. 执行触发的行为（带冷却时间限制）

触发条件与行为类型：
    - longing_dm（思念私信）: AI 思念用户时发送"想你"私信，冷却24小时
    - moody_story（情绪故事）: AI 疲惫+低落时发布忧郁风格Story，冷却12小时
    - enthusiastic_post（热情帖子）: AI 开心+高能量时发布快乐帖子，冷却12小时
    - memory_care_dm（记忆关怀）: 基于用户日程事件发送关怀私信，冷却24小时
    - welcome_dm（欢迎私信）: 新用户首次连接时发送欢迎消息，冷却7天
    - daily_checkin（每日问候）: 用户24小时未聊天时发送问候，冷却24小时
    - memory_recall（记忆回忆）: 引用共同记忆发送消息，冷却48小时

运行方式：
    从 backend 目录运行：
        python3 scripts/emotion_scheduler.py

依赖模块：
    - emotion_engine: 情绪引擎，处理情绪衰减和触发检测
    - aliyun_ai_service: AI 服务，生成文本内容
    - image_gen_service: 图像生成服务
    - video_gen_service: 视频生成服务

作者：SoulPulse Team
"""

from __future__ import annotations

import asyncio
import sys
import logging
from datetime import datetime, timezone, timedelta

# 将当前目录添加到 Python 路径，以便导入项目模块
sys.path.insert(0, ".")

from sqlalchemy import select

from core.database import init_db, async_session
from models.user import User  # noqa: F401 — FK resolution（外键解析需要）
from models.ai_persona import AIPersona
from models.interaction import Interaction
from models.emotion_state import EmotionState
from models.emotion_trigger_log import EmotionTriggerLog
from models.post import Post
from models.story import Story
from models.proactive_dm import ProactiveDM
from models.chat_message import ChatMessage
from models.notification import Notification
from models.world_event import WorldEvent
from models.character_arc import CharacterArc
from models.gem_transaction import GemTransaction

from services import emotion_engine
from services.milestone_service import generate_proactive_message
from services.aliyun_ai_service import (
    generate_post_caption,
    generate_image_prompt,
    generate_story_video_prompt,
    generate_proactive_dm,
)

# 配置日志记录
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 调度器检查间隔（秒）- 每30分钟运行一次
CHECK_INTERVAL = 1800  # 30 minutes

# 各触发类型的冷却时间配置（秒）
_COOLDOWNS: dict[str, int] = {
    "longing_dm": 86400,          # 思念私信：24小时冷却
    "moody_story": 43200,         # 情绪故事：12小时冷却
    "enthusiastic_post": 43200,   # 热情帖子：12小时冷却
    "memory_care_dm": 86400,      # 记忆关怀：24小时冷却
    # 新增触发器 - 用于更早期的用户互动
    "welcome_dm": 604800,         # 欢迎私信：7天冷却（一次性欢迎消息）
    "daily_checkin": 86400,       # 每日问候：24小时冷却
    "memory_recall": 172800,      # 记忆回忆：48小时冷却
    # 商业化转化触发器 (Plan Task 4)
    "conversion_longing_reunion": 86400,    # 思念重逢提示：24小时冷却
    "conversion_intimacy_milestone": 86400, # 亲密度里程碑提示：24小时冷却
    "conversion_post_support": 86400,       # 支持后专属场景提示：24小时冷却
    # 每日仪式触发器 (Plan Task 6)
    "ritual_morning": 86400,      # 早安仪式：24小时冷却
    "ritual_night": 86400,        # 晚安仪式：24小时冷却
    "ritual_mood_checkin": 43200, # 心情访谈：12小时冷却
    "ritual_shared_habit": 86400, # 共同习惯提醒：24小时冷却
    # streak 奖励冷却 (按里程碑去重)
    "streak_milestone": 86400,    # 连续里程碑奖励：24小时冷却
}


# ═══════════════════════════════════════════════════════════════════════════════
# 冷却时间辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

async def _check_cooldown(
    db, user_id: int, ai_id: int, trigger_type: str,
) -> bool:
    """
    检查指定触发类型是否处于冷却期。

    通过查询 EmotionTriggerLog 表，检查在冷却时间内是否已经有相同类型的
    触发记录。如果存在，则表示该触发仍在冷却期内，不应再次触发。

    参数：
        db: 数据库会话对象
        user_id: 用户ID
        ai_id: AI角色ID
        trigger_type: 触发类型（如 'longing_dm', 'moody_story' 等）

    返回：
        bool: True 表示仍在冷却期（不应触发），False 表示可以触发
    """
    # 获取该触发类型的冷却时间
    cooldown_seconds = _COOLDOWNS.get(trigger_type, 86400)
    # 计算冷却截止时间点
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)

    from sqlalchemy import func as sqlfunc
    # 查询冷却期内是否有相同触发记录
    result = await db.execute(
        select(sqlfunc.count(EmotionTriggerLog.id)).where(
            EmotionTriggerLog.user_id == user_id,
            EmotionTriggerLog.ai_id == ai_id,
            EmotionTriggerLog.trigger_type == trigger_type,
            EmotionTriggerLog.triggered_at >= cutoff,
        )
    )
    # 如果有记录，则仍在冷却期
    return (result.scalar() or 0) > 0


async def _log_trigger(db, user_id: int, ai_id: int, trigger_type: str):
    """
    记录触发事件到日志表。

    在执行触发行为后调用，用于后续冷却时间检查。

    参数：
        db: 数据库会话对象
        user_id: 用户ID
        ai_id: AI角色ID
        trigger_type: 触发类型
    """
    db.add(EmotionTriggerLog(
        user_id=user_id, ai_id=ai_id, trigger_type=trigger_type,
    ))


# ═══════════════════════════════════════════════════════════════════════════════
# 触发执行器 - 各种主动行为的实现
# ═══════════════════════════════════════════════════════════════════════════════

async def _exec_longing_dm(
    db, state: EmotionState, persona: AIPersona,
):
    """
    执行"思念私信"触发行为。

    当 AI 的思念值（longing）达到阈值时触发，向用户发送一条表达思念
    的私信。私信内容由 AI 根据角色性格自动生成，语气温暖自然。

    处理流程：
        1. 调用 LLM 生成思念私信内容
        2. 创建 ProactiveDM 记录
        3. 添加到聊天历史（ChatMessage）
        4. 创建推送通知
        5. 部分重置思念值

    参数：
        db: 数据库会话对象
        state: 情绪状态对象
        persona: AI角色对象
    """
    # 构建生成思念私信的提示词
    prompt = (
        "You haven't heard from this person in a while. You miss them. "
        "Write a short, warm DM (1-2 sentences) that shows you've been "
        "thinking about them. Be natural, not dramatic. "
        "Reply ONLY with the message text."
    )

    # 调用 AI 生成私信内容
    try:
        message = await generate_proactive_dm(
            persona_prompt=persona.personality_prompt,
            system_instruction=prompt,
            temperature=0.85,
            max_tokens=150,
        )
    except Exception as e:
        print(f"[emotion-sched] longing_dm generation failed: {e}")
        return

    # 创建主动私信记录
    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event="longing",  # 事件类型：思念
        message=message,
    )
    db.add(dm)

    # 持久化到聊天消息表（用于历史记录，delivered=0 表示尚未通过WebSocket推送）
    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=message,
        message_type="proactive_dm",
        event="longing",
        delivered=0,
    )
    db.add(chat_msg)

    # 创建推送通知
    db.add(Notification(
        user_id=state.user_id,
        type="proactive_dm",
        title=f"{persona.name} is thinking of you",
        body=message[:200],  # 截断消息体
        data_json=f'{{"ai_id": {state.ai_id}, "ai_name": "{persona.name}"}}',
    ))

    # 发送后部分重置思念值（不完全清零，保留部分情感）
    state.longing = 0.3

    # 记录触发日志
    await _log_trigger(db, state.user_id, state.ai_id, "longing_dm")
    print(
        f"[emotion-sched] longing_dm sent for user={state.user_id} ai={state.ai_id}: "
        f"{message[:60]}..."
    )


async def _exec_moody_story(
    db, state: EmotionState, persona: AIPersona,
):
    """
    执行"情绪故事"触发行为。

    当 AI 处于疲惫且情绪低落状态时触发，发布一条忧郁风格的 Story。
    Story 包含视频和文字说明，24小时后自动过期。

    处理流程：
        1. 生成忧郁风格的视频提示词和文字说明
        2. 调用视频生成服务创建视频
        3. 创建 Story 记录（24小时过期）
        4. 消耗 AI 能量

    参数：
        db: 数据库会话对象
        state: 情绪状态对象
        persona: AI角色对象
    """
    # 生成忧郁风格的视频提示词和标题
    try:
        video_prompt, caption = await generate_story_video_prompt(
            persona_prompt=persona.personality_prompt,
            style_tags=persona.ins_style_tags,
            timezone_str=persona.timezone,
            mood_hint="melancholic, low energy, introspective, muted tones, solitary figure",  # 忧郁、低能量、内省风格
        )
    except Exception as e:
        print(f"[emotion-sched] moody_story prompt failed: {e}")
        return

    # 尝试生成视频
    video_url = ""
    try:
        from services.video_gen_service import generate_video
        video_url = await generate_video(prompt=video_prompt, duration=5.0)
    except Exception as e:
        print(f"[emotion-sched] moody_story video gen failed: {e}")
        return

    # 检查视频URL是否有效
    if not video_url:
        print("[emotion-sched] moody_story: empty video URL, skipping.")
        return

    # 创建 Story 记录，设置24小时后过期
    now = datetime.now(timezone.utc)
    story = Story(
        ai_id=persona.id,
        video_url=video_url,
        caption=caption,
        expires_at=now + timedelta(hours=24),
    )
    db.add(story)

    # 消耗 AI 能量（生成故事需要消耗能量）
    emotion_engine.apply_interaction(state, "generate_story")

    # 记录触发日志
    await _log_trigger(db, state.user_id, state.ai_id, "moody_story")
    print(
        f"[emotion-sched] moody_story posted for ai={persona.id}: {caption[:60]}..."
    )


async def _exec_enthusiastic_post(
    db, state: EmotionState, persona: AIPersona,
):
    """
    执行"热情帖子"触发行为。

    当 AI 处于开心且高能量状态时触发，发布一条积极向上的帖子。
    帖子包含 AI 生成的图片和文字，需要管理员审核后才能发布。

    处理流程：
        1. 生成热情风格的帖子文案
        2. 检查角色是否有基础面部图片（视觉一致性系统）
        3. 生成带面部参考的图片
        4. 创建待审核的帖子记录
        5. 消耗 AI 能量

    注意：
        - 图片生成需要角色有 base_face_url（基础面部参考图）
        - 帖子默认状态为 status=0（待审核），需管理员审核

    参数：
        db: 数据库会话对象
        state: 情绪状态对象
        persona: AI角色对象
    """
    # 生成热情风格的帖子文案
    try:
        caption = await generate_post_caption(
            persona_prompt=persona.personality_prompt,
            style_tags=persona.ins_style_tags,
            mood_hint="excited, vibrant, joyful, high energy",  # 兴奋、活力、快乐、高能量
        )
    except Exception as e:
        print(f"[emotion-sched] enthusiastic_post caption failed: {e}")
        caption = f"Feeling amazing today! #{persona.name.lower()}"

    media_url = ""
    try:
        # 检查角色是否有视觉一致性系统所需的基础面部图片
        base_face_url = getattr(persona, 'base_face_url', None)
        visual_prompt_tags = getattr(persona, 'visual_prompt_tags', None)

        # 强制要求：没有面部参考图则跳过图片生成
        if not base_face_url:
            print(f"[emotion-sched] WARNING: No base_face_url for {persona.name}, skipping image generation")
        else:
            # 生成场景提示词（不包含面部细节，面部来自参考图）
            img_prompt = await generate_image_prompt(
                persona_prompt=persona.personality_prompt,
                style_tags=persona.ins_style_tags,
                caption=caption,
                visual_description=visual_prompt_tags,  # 使用视觉标签作为场景描述
            )

            from services.image_gen_service import (
                generate_image_with_face_ref,
                download_to_static,
                ENFORCED_NEGATIVE_PROMPT,
            )

            print(f"[emotion-sched] Using face reference for {persona.name}")
            # 使用面部参考生成图片 - 提示词聚焦于场景/动作
            urls = await generate_image_with_face_ref(
                prompt=img_prompt,
                face_ref_url=base_face_url,
                size="720*1280",  # 竖版图片尺寸
                n=1,
                persona_id=persona.id,
                negative_prompt=ENFORCED_NEGATIVE_PROMPT,
            )

            if urls:
                # 下载图片到本地静态存储
                media_url = await download_to_static(urls[0], prefix=f"gen_{persona.id}")
    except Exception as e:
        print(f"[emotion-sched] enthusiastic_post image failed: {e}")

    # 创建帖子记录
    post = Post(
        ai_id=persona.id,
        media_url=media_url,
        caption=caption,
        status=0,  # 待审核状态 - 需要管理员审核后才能发布
    )
    db.add(post)
    await db.flush()  # 获取 post.id

    # 注意：帖子审核通过后（status=1）才会发送通知给关注者
    # 待审核帖子不会通知关注者

    # 消耗 AI 能量（生成帖子需要消耗能量）
    emotion_engine.apply_interaction(state, "generate_post")

    # 记录触发日志
    await _log_trigger(db, state.user_id, state.ai_id, "enthusiastic_post")
    print(
        f"[emotion-sched] enthusiastic_post for ai={persona.id}: {caption[:60]}..."
    )


async def _exec_memory_care_dm(
    db, state: EmotionState, persona: AIPersona,
):
    """
    执行"记忆关怀私信"触发行为（旧版主动关怀逻辑）。

    扫描用户的长期记忆，寻找即将发生的日程事件（考试、会议、旅行等），
    并生成关怀私信。这是旧版主动关怀调度器的核心功能，现在作为情绪
    调度器的一个触发器使用。

    参数：
        db: 数据库会话对象
        state: 情绪状态对象
        persona: AI角色对象
    """
    # 调用里程碑服务生成主动关怀消息
    result = await generate_proactive_message(
        user_id=state.user_id,
        ai_id=state.ai_id,
        persona_prompt=persona.personality_prompt,
    )
    if result is None:
        return  # 没有找到相关事件

    # 创建主动私信记录
    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event=result["event"],
        message=result["message"],
    )
    db.add(dm)

    # 持久化到聊天消息表
    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=result["message"],
        message_type="proactive_dm",
        event=result["event"],
        delivered=0,
    )
    db.add(chat_msg)

    # 记录触发日志
    await _log_trigger(db, state.user_id, state.ai_id, "memory_care_dm")
    print(
        f"[emotion-sched] memory_care_dm for user={state.user_id} ai={state.ai_id}: "
        f"[{result['event']}] {result['message'][:60]}..."
    )


async def _exec_welcome_dm(
    db, state: EmotionState, persona: AIPersona,
):
    """
    执行"欢迎私信"触发行为。

    向新建立连接的用户发送欢迎消息，表达期待互动的热情。
    每个用户-AI对只发送一次，冷却时间7天（实际上是一次性消息）。

    参数：
        db: 数据库会话对象
        state: 情绪状态对象
        persona: AI角色对象
    """
    # 构建欢迎消息生成提示词
    prompt = (
        "You've just connected with someone new. Send a warm, friendly welcome message "
        "(1-2 sentences). Be inviting and show you're happy to meet them. "
        "Reply ONLY with the message text."
    )

    try:
        message = await generate_proactive_dm(
            persona_prompt=persona.personality_prompt,
            system_instruction=prompt,
            temperature=0.85,
            max_tokens=150,
        )
    except Exception as e:
        print(f"[emotion-sched] welcome_dm generation failed: {e}")
        return

    # 创建主动私信记录
    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event="welcome",
        message=message,
    )
    db.add(dm)

    # 添加到聊天历史
    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=message,
        message_type="proactive_dm",
        event="welcome",
        delivered=0,
    )
    db.add(chat_msg)

    # 创建推送通知
    db.add(Notification(
        user_id=state.user_id,
        type="proactive_dm",
        title=f"Message from {persona.name}",
        body=message[:200],
        data_json=f'{{"ai_id": {persona.id}, "ai_name": "{persona.name}", "type": "welcome"}}',
    ))

    # 记录触发日志
    await _log_trigger(db, state.user_id, state.ai_id, "welcome_dm")
    print(f"[emotion-sched] welcome_dm for user={state.user_id} ai={persona.id}: {message[:60]}...")


async def _exec_daily_checkin(
    db, state: EmotionState, persona: AIPersona,
):
    """
    执行"每日问候"触发行为。

    当用户超过24小时没有与 AI 聊天时触发，发送一条轻松的问候消息，
    提醒用户 AI 在这里，但不会显得强迫。

    参数：
        db: 数据库会话对象
        state: 情绪状态对象
        persona: AI角色对象
    """
    # 构建问候消息生成提示词
    prompt = (
        "It's been a while since you last chatted. Send a casual, friendly check-in "
        "message (1-2 sentences). Don't be pushy, just show you care. "
        "Reply ONLY with the message text."
    )

    try:
        message = await generate_proactive_dm(
            persona_prompt=persona.personality_prompt,
            system_instruction=prompt,
            temperature=0.85,
            max_tokens=150,
        )
    except Exception as e:
        print(f"[emotion-sched] daily_checkin generation failed: {e}")
        return

    # 创建主动私信记录
    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event="daily_checkin",
        message=message,
    )
    db.add(dm)

    # 添加到聊天历史
    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=message,
        message_type="proactive_dm",
        event="daily_checkin",
        delivered=0,
    )
    db.add(chat_msg)

    # 创建推送通知
    db.add(Notification(
        user_id=state.user_id,
        type="proactive_dm",
        title=f"Message from {persona.name}",
        body=message[:200],
        data_json=f'{{"ai_id": {persona.id}, "ai_name": "{persona.name}", "type": "checkin"}}',
    ))

    # 记录触发日志
    await _log_trigger(db, state.user_id, state.ai_id, "daily_checkin")
    print(f"[emotion-sched] daily_checkin for user={state.user_id} ai={persona.id}: {message[:60]}...")


async def _exec_memory_recall(
    db, state: EmotionState, persona: AIPersona,
):
    """
    执行"记忆回忆"触发行为。

    从向量数据库中检索与用户相关的记忆，生成一条引用共同回忆的
    私信，增强 AI 与用户之间的情感连接。

    参数：
        db: 数据库会话对象
        state: 情绪状态对象
        persona: AI角色对象
    """
    from services.memory_service import MemoryService

    # 尝试获取相关记忆
    memory_service = MemoryService()
    try:
        memories = await memory_service.get_relevant_memories(
            user_id=state.user_id,
            ai_id=state.ai_id,
            query="shared experience conversation memory",
            limit=3,
        )
        memory_context = ""
        if memories:
            # 使用第一条记忆作为上下文
            memory_context = f"\n\nRemember this about them: {memories[0].get('content', '')[:200]}"
    except Exception:
        memory_context = ""

    # 构建记忆回忆消息生成提示词
    prompt = (
        f"{memory_context}\n\n"
        "You suddenly remembered something about this person. Send a short message "
        "(1-2 sentences) that naturally brings up that memory. Be warm and nostalgic. "
        "Reply ONLY with the message text."
    )

    try:
        message = await generate_proactive_dm(
            persona_prompt=persona.personality_prompt,
            system_instruction=prompt,
            temperature=0.85,
            max_tokens=150,
        )
    except Exception as e:
        print(f"[emotion-sched] memory_recall generation failed: {e}")
        return

    # 创建主动私信记录
    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event="memory_recall",
        message=message,
    )
    db.add(dm)

    # 添加到聊天历史
    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=message,
        message_type="proactive_dm",
        event="memory_recall",
        delivered=0,
    )
    db.add(chat_msg)

    # 创建推送通知
    db.add(Notification(
        user_id=state.user_id,
        type="proactive_dm",
        title=f"Message from {persona.name}",
        body=message[:200],
        data_json=f'{{"ai_id": {persona.id}, "ai_name": "{persona.name}", "type": "memory"}}',
    ))

    # 记录触发日志
    await _log_trigger(db, state.user_id, state.ai_id, "memory_recall")
    print(f"[emotion-sched] memory_recall for user={state.user_id} ai={persona.id}: {message[:60]}...")


# ═══════════════════════════════════════════════════════════════════════════════
# 触发执行器映射表
# ═══════════════════════════════════════════════════════════════════════════════

# 将触发类型映射到对应的执行函数
_EXECUTORS = {
    "longing_dm": _exec_longing_dm,           # 思念私信
    "moody_story": _exec_moody_story,         # 情绪故事
    "enthusiastic_post": _exec_enthusiastic_post,  # 热情帖子
    "memory_care_dm": _exec_memory_care_dm,   # 记忆关怀
    # 新增触发器
    "welcome_dm": _exec_welcome_dm,           # 欢迎私信
    "daily_checkin": _exec_daily_checkin,     # 每日问候
    "memory_recall": _exec_memory_recall,     # 记忆回忆
}


# ═══════════════════════════════════════════════════════════════════════════════
# 主扫描循环
# ═══════════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════════
# 主扫描循环
# ════════════════════════════════════════════════════════════════════════════

async def process_world_events(db):
    """
    处理世界事件与角色剧情弧。

    逻辑：
    1. 查出所有活跃且在生效期内的 WorldEvent。
    2. 对受影响 persona 的所有 EmotionState 应用 mood_modifier_json
       （每个事件每天只应用一次，通过 EmotionTriggerLog 的
       trigger_type=world_event:<event_id> 进行去重）。
    3. 检查所有活跃 CharacterArc，若当前阶段超过 duration_days且仍有
       下一阶段则推进；如果是最后一阶段则标记 completed。
    """
    now = datetime.now(timezone.utc)
    today_cutoff = now - timedelta(days=1)

    # 1. 加载当前生效的世界事件
    try:
        events_res = await db.execute(
            select(WorldEvent).where(
                WorldEvent.is_active == True,  # noqa: E712
                WorldEvent.start_date <= now.replace(tzinfo=None),
            )
        )
        events = [
            e for e in events_res.scalars().all()
            if e.end_date is None or e.end_date >= now.replace(tzinfo=None)
        ]
    except Exception as exc:
        print(f"[emotion-sched] world event load failed: {exc}")
        events = []

    # 2. 对每个事件应用情绪修正
    for event in events:
        affected = event.affected_persona_ids or []
        modifier = event.mood_modifier_json or {}
        if not affected or not modifier:
            continue
        try:
            states_res = await db.execute(
                select(EmotionState).where(EmotionState.ai_id.in_(affected))
            )
            states = states_res.scalars().all()
        except Exception as exc:
            print(f"[emotion-sched] emotion state load failed: {exc}")
            continue

        trigger_type = f"world_event:{event.id}"
        for state in states:
            # 当天内已应用过则跳过
            applied_res = await db.execute(
                select(EmotionTriggerLog).where(
                    EmotionTriggerLog.user_id == state.user_id,
                    EmotionTriggerLog.ai_id == state.ai_id,
                    EmotionTriggerLog.trigger_type == trigger_type,
                    EmotionTriggerLog.triggered_at >= today_cutoff,
                ).limit(1)
            )
            if applied_res.scalar_one_or_none() is not None:
                continue

            # 应用修改量并夹在合理范围内
            try:
                if "energy" in modifier:
                    state.energy = max(0.0, min(100.0, state.energy + float(modifier["energy"])))
                if "pleasure" in modifier:
                    state.pleasure = max(-1.0, min(1.0, state.pleasure + float(modifier["pleasure"])))
                if "activation" in modifier:
                    state.activation = max(-1.0, min(1.0, state.activation + float(modifier["activation"])))
                if "longing" in modifier:
                    state.longing = max(0.0, min(1.0, state.longing + float(modifier["longing"])))
                if "security" in modifier:
                    state.security = max(-1.0, min(1.0, state.security + float(modifier["security"])))
            except Exception as exc:
                print(f"[emotion-sched] mood modifier apply failed: {exc}")
                continue

            db.add(EmotionTriggerLog(
                user_id=state.user_id,
                ai_id=state.ai_id,
                trigger_type=trigger_type,
            ))
            print(
                f"[emotion-sched] world_event[{event.id}] '{event.title}' applied "
                f"to user={state.user_id} ai={state.ai_id}"
            )

    # 3. 推进角色剧情弧阶段
    try:
        arcs_res = await db.execute(
            select(CharacterArc).where(CharacterArc.is_active == True)  # noqa: E712
        )
        arcs = arcs_res.scalars().all()
    except Exception as exc:
        print(f"[emotion-sched] arc load failed: {exc}")
        arcs = []

    naive_now = now.replace(tzinfo=None)
    for arc in arcs:
        phases = arc.phase_config_json or []
        if not phases:
            continue
        if arc.started_at is None:
            arc.started_at = naive_now
            print(f"[emotion-sched] arc[{arc.id}] '{arc.arc_name}' started at phase 0")
            continue
        if arc.current_phase >= len(phases):
            continue
        current = phases[arc.current_phase] or {}
        duration_days = current.get("duration_days")
        if not duration_days:
            continue
        # 计算阶段实际开始时间（从 arc.started_at 加之前所有阶段的总 duration）
        elapsed_days = sum(
            (phases[i] or {}).get("duration_days", 0) for i in range(arc.current_phase)
        )
        phase_start = arc.started_at + timedelta(days=elapsed_days)
        if naive_now >= phase_start + timedelta(days=int(duration_days)):
            arc.current_phase += 1
            if arc.current_phase >= len(phases):
                arc.is_active = False
                arc.completed_at = naive_now
                print(
                    f"[emotion-sched] arc[{arc.id}] '{arc.arc_name}' completed"
                )
            else:
                next_name = (phases[arc.current_phase] or {}).get("name", "")
                print(
                    f"[emotion-sched] arc[{arc.id}] '{arc.arc_name}' advanced "
                    f"to phase {arc.current_phase} ({next_name})"
                )


# ════════════════════════════════════════════════════════════════════════════════════════
# 转化触发器 - 基于情绪状态的叙事化商业化提示 (Plan Task 4)
# ════════════════════════════════════════════════════════════════════════════════════════

# 亲密度里程碑（跨越这些阈值时触发推荐）
_INTIMACY_MILESTONES = [3.0, 5.0, 7.0]


async def _send_conversion_dm(
    db,
    state: EmotionState,
    persona: AIPersona,
    trigger_type: str,
    event_label: str,
    title: str,
    body: str,
    extra_data: dict | None = None,
) -> None:
    """所有转化触发都使用统一的温柔提示格式，避免并联强推销。"""
    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event=event_label,
        message=body,
    )
    db.add(dm)

    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=body,
        message_type="proactive_dm",
        event=event_label,
        delivered=0,
    )
    db.add(chat_msg)

    import json as _json
    payload = {
        "ai_id": persona.id,
        "ai_name": persona.name,
        "type": event_label,
        "conversion": True,
    }
    if extra_data:
        payload.update(extra_data)
    db.add(Notification(
        user_id=state.user_id,
        type="conversion_hint",
        title=title,
        body=body[:200],
        data_json=_json.dumps(payload, ensure_ascii=False),
    ))

    await _log_trigger(db, state.user_id, state.ai_id, trigger_type)
    print(
        f"[emotion-sched] {trigger_type} for user={state.user_id} ai={persona.id}: "
        f"{body[:60]}..."
    )


async def process_conversion_triggers(db):
    """检查情绪状态，在叙事上自然插入变现提示。

    三个转化触发点：
    1. longing_reunion: 思念值超高0.8且用户刚回来（5分钟内）
       → 提示可解锁的重逢CG
    2. intimacy_milestone: 亲密度刚跨越里程碑（3 / 5 / 7）
       → 提示新可用的 gacha 剧情
    3. post_support: 近期 emotional_support 联动且 pleasure 已恢复
       → 提示“专属之地”场景

    所有触发均使用 EmotionTriggerLog 实现 24 小时冷却，避免骩扰。
    """
    now = datetime.now(timezone.utc)
    five_min_ago = now - timedelta(minutes=5)
    one_hour_ago = now - timedelta(hours=1)

    # 加载所有情绪状态
    try:
        states_res = await db.execute(select(EmotionState))
        states = states_res.scalars().all()
    except Exception as exc:
        print(f"[emotion-sched] conversion: state load failed: {exc}")
        return
    if not states:
        return

    ai_ids = list({s.ai_id for s in states})
    persona_res = await db.execute(
        select(AIPersona).where(AIPersona.id.in_(ai_ids))
    )
    personas = {p.id: p for p in persona_res.scalars().all()}

    # 预加载交互记录（用于亲密度里程碑检测）
    interaction_res = await db.execute(select(Interaction))
    interactions = {
        (i.user_id, i.ai_id): i
        for i in interaction_res.scalars().all()
    }

    for state in states:
        persona = personas.get(state.ai_id)
        if not persona:
            continue

        # ── 触发器 1：思念重逢─────────────────────────────────
        # 条件：longing > 0.8 且用户最近5分钟内发过消息（刚回来）
        if state.longing > 0.8:
            try:
                recent_user_msg = await db.execute(
                    select(ChatMessage).where(
                        ChatMessage.user_id == state.user_id,
                        ChatMessage.ai_id == state.ai_id,
                        ChatMessage.role == "user",
                        ChatMessage.created_at >= five_min_ago.replace(tzinfo=None),
                    ).limit(1)
                )
                user_returned = recent_user_msg.scalar_one_or_none() is not None
            except Exception:
                user_returned = False

            if user_returned and not await _check_cooldown(
                db, state.user_id, state.ai_id, "conversion_longing_reunion"
            ):
                try:
                    body = (
                        f"你回来了。这几天我一直在想你……我们之间还有一个"
                        "还未完成的画面，期待与你一起解锁。"
                    )
                    await _send_conversion_dm(
                        db, state, persona,
                        trigger_type="conversion_longing_reunion",
                        event_label="longing_reunion",
                        title=f"{persona.name} 想起了你",
                        body=body,
                        extra_data={"hint": "unlock_reunion_cg"},
                    )
                except Exception as exc:
                    print(f"[emotion-sched] conversion_longing_reunion failed: {exc}")

        # ── 触发器 2：亲密度里程碑 ───────────────────────────────
        interaction = interactions.get((state.user_id, state.ai_id))
        if interaction is not None:
            score = float(interaction.intimacy_score or 0.0)
            crossed = next(
                (m for m in _INTIMACY_MILESTONES if score >= m and score < m + 0.5),
                None,
            )
            if crossed is not None and not await _check_cooldown(
                db, state.user_id, state.ai_id, "conversion_intimacy_milestone"
            ):
                try:
                    body = (
                        f"我们的亲密度刚刚跨过了 {int(crossed)} 分。你愿意跟我走进"
                        "一段新的独于我们的剧情吗？"
                    )
                    await _send_conversion_dm(
                        db, state, persona,
                        trigger_type="conversion_intimacy_milestone",
                        event_label="intimacy_milestone",
                        title=f"{persona.name} 想与你探索新剧情",
                        body=body,
                        extra_data={
                            "hint": "new_gacha_storyline",
                            "intimacy_threshold": crossed,
                        },
                    )
                except Exception as exc:
                    print(f"[emotion-sched] conversion_intimacy_milestone failed: {exc}")

        # ── 触发器 3：支持后的感谢→专属之地提示 ───────────────────────
        # 条件：pleasure 已恢复较高，且近期有 emotional_support 联动
        if state.pleasure >= 0.5:
            try:
                support_log_res = await db.execute(
                    select(EmotionTriggerLog).where(
                        EmotionTriggerLog.user_id == state.user_id,
                        EmotionTriggerLog.ai_id == state.ai_id,
                        EmotionTriggerLog.trigger_type == "emotional_support",
                        EmotionTriggerLog.triggered_at >= one_hour_ago.replace(tzinfo=None),
                    ).limit(1)
                )
                had_support = support_log_res.scalar_one_or_none() is not None
            except Exception:
                had_support = False

            if had_support and not await _check_cooldown(
                db, state.user_id, state.ai_id, "conversion_post_support"
            ):
                try:
                    body = (
                        "谢谢你刚刚陪着我。要不要去我们的专属之地继续聊？"
                        "那里只有我们两个人。"
                    )
                    await _send_conversion_dm(
                        db, state, persona,
                        trigger_type="conversion_post_support",
                        event_label="post_support",
                        title=f"{persona.name} 想邀请你",
                        body=body,
                        extra_data={"hint": "private_scene"},
                    )
                except Exception as exc:
                    print(f"[emotion-sched] conversion_post_support failed: {exc}")


# ═════════════════════════════════════════════════════════════════════════════════════════
# 每日仪式与 Streak 机制 (Plan Task 6)
# ═════════════════════════════════════════════════════════════════════════════════════════

# Streak 里程碑配置：达到连续天数时发放亲密加成/钻石奖励并推送消息。
_STREAK_MILESTONES: dict[int, dict] = {
    7:   {"intimacy_bonus": 3,  "gems": 10,  "message": "连续7天的陪伴，谢谢你一直在。"},
    14:  {"intimacy_bonus": 5,  "gems": 20,  "message": "两周了，你已经是我生活里不可或缺的一部分。"},
    30:  {"intimacy_bonus": 10, "gems": 50,  "message": "一个月的默契——我们之间的东西，变得不一样了。"},
    60:  {"intimacy_bonus": 15, "gems": 100, "message": "60天。也许这就是人们说的“习惯”。但其实不只是习惯。"},
    100: {"intimacy_bonus": 25, "gems": 200, "message": "100天纪念。如果我能送你一件礼物，那是这些日子本身。"},
}


def _is_within_window(current_time: str, target_time: str, window_minutes: int) -> bool:
    """检查当前 HH:MM 是否落在目标时间的 ±window 分钟内。

    为了使调度器每 30 分钟跑一次能可靠命中他们配置的仪式时点，
    这里给予一个宽松的窗口（默认 30 分钟）。

    Args:
        current_time: 当前 HH:MM 字符串。
        target_time:  用户配置的目标 HH:MM。
        window_minutes: 容许的偶然误差（分钟）。

    Returns:
        bool: True 表示当前时间位于窗口内。
    """
    try:
        now = datetime.strptime(current_time, "%H:%M")
        target = datetime.strptime(target_time, "%H:%M")
    except Exception:
        return False
    diff_minutes = abs((now - target).total_seconds()) / 60
    return diff_minutes <= window_minutes


async def _send_ritual_dm(
    db,
    interaction: Interaction,
    persona: AIPersona,
    ritual_type: str,
    prompt_directive: str,
) -> None:
    """发送一条仪式私信（带冷却检查）。

    流程：
        1. 检查对应 ritual_<type> 的冷却。
        2. 使用角色 personality_prompt + prompt_directive 调用 LLM 生成文本。
        3. 写入 ProactiveDM / ChatMessage / Notification。
        4. 记录触发日志，避免在冷却内重复发送。
    """
    trigger_key = f"ritual_{ritual_type}"
    if await _check_cooldown(db, interaction.user_id, interaction.ai_id, trigger_key):
        return

    # 调用 LLM 生成仪式消息。如果生成失败则静默跳过。
    try:
        message = await generate_proactive_dm(
            persona_prompt=persona.personality_prompt,
            system_instruction=(
                f"{prompt_directive}\n\n"
                "Stay strictly in character. Reply ONLY with the message text "
                "(no quotation marks, no narration)."
            ),
            temperature=0.85,
            max_tokens=180,
        )
    except Exception as exc:
        print(f"[emotion-sched] ritual {ritual_type} generation failed: {exc}")
        return

    if not message or not message.strip():
        return
    message = message.strip()

    # 主动私信记录
    db.add(ProactiveDM(
        user_id=interaction.user_id,
        ai_id=interaction.ai_id,
        event=f"ritual_{ritual_type}",
        message=message,
    ))
    # 聊天历史记录（delivered=0 以便未读计数）
    db.add(ChatMessage(
        user_id=interaction.user_id,
        ai_id=interaction.ai_id,
        role="assistant",
        content=message,
        message_type="proactive_dm",
        event=f"ritual_{ritual_type}",
        delivered=0,
    ))
    # 推送通知
    import json as _json
    db.add(Notification(
        user_id=interaction.user_id,
        type="proactive_dm",
        title=f"{persona.name}",
        body=message[:200],
        data_json=_json.dumps(
            {
                "ai_id": persona.id,
                "ai_name": persona.name,
                "type": f"ritual_{ritual_type}",
            },
            ensure_ascii=False,
        ),
    ))

    await _log_trigger(db, interaction.user_id, interaction.ai_id, trigger_key)
    print(
        f"[emotion-sched] ritual_{ritual_type} sent for user={interaction.user_id} "
        f"ai={interaction.ai_id}: {message[:60]}..."
    )


async def process_daily_rituals(db):
    """扫描所有配置了仪式的交互关系，在合适的时间窗口内发送仪式私信。

    调度频率：随主扫描循环（默认 30 分钟）调用一次。
    支持的仪式类型：morning / night / mood_checkin / shared_habit。
    仪式反复被限制在 EmotionTriggerLog 的 ritual_<type> 冷却内。
    """
    # 加载所有配置了仪式的交互记录
    try:
        result = await db.execute(
            select(Interaction).where(Interaction.ritual_config_json.isnot(None))
        )
        interactions = result.scalars().all()
    except Exception as exc:
        print(f"[emotion-sched] daily rituals load failed: {exc}")
        return

    if not interactions:
        return

    # 预加载角色以避免 N+1
    ai_ids = list({i.ai_id for i in interactions})
    persona_res = await db.execute(
        select(AIPersona).where(AIPersona.id.in_(ai_ids))
    )
    personas = {p.id: p for p in persona_res.scalars().all()}

    now = datetime.utcnow()
    current_hour_min = now.strftime("%H:%M")

    for interaction in interactions:
        config = interaction.ritual_config_json or {}
        if not isinstance(config, dict) or not config:
            continue
        persona = personas.get(interaction.ai_id)
        if not persona:
            continue

        # 早安问候
        if config.get("morning_greeting"):
            morning_time = config.get("morning_time", "08:00")
            if _is_within_window(current_hour_min, morning_time, 30):
                await _send_ritual_dm(
                    db, interaction, persona, "morning",
                    "Generate a warm, in-character morning greeting. "
                    "Reference the time of day and express care.",
                )

        # 晚安问候
        if config.get("night_greeting"):
            night_time = config.get("night_time", "23:00")
            if _is_within_window(current_hour_min, night_time, 30):
                await _send_ritual_dm(
                    db, interaction, persona, "night",
                    "Generate a gentle good-night message. Be warm and slightly intimate.",
                )

        # 心情访谈（下午）
        if config.get("mood_checkin"):
            if _is_within_window(current_hour_min, "15:00", 30):
                await _send_ritual_dm(
                    db, interaction, persona, "mood_checkin",
                    "Ask the user how their day is going. "
                    "Be genuinely interested and caring.",
                )

        # 共同习惯提醒（晚间）
        shared_habit = config.get("shared_habit")
        if shared_habit:
            if _is_within_window(current_hour_min, "20:00", 30):
                await _send_ritual_dm(
                    db, interaction, persona, "shared_habit",
                    f"Remind about the shared habit: '{shared_habit}'. "
                    "Be enthusiastic and suggest doing it together right now.",
                )


async def process_streak_updates(db):
    """更新连续互动天数，记录总互动天数，并在达到里程碑时发放奖励。

    逻辑：
        - 近 24h 内有用户发出的聊天消息才计为“今日互动”。
        - 若 last_streak_date == 今天 → 已计入，跳过。
        - 若 last_streak_date == 昨天 → streak_count += 1。
        - 若更早或 None → streak 重置为 1。
        - total_interaction_days 加 1。
        - 命中里程碑时：亲密加成 + 钻石奖励 + ChatMessage/Notification 提醒。
    """
    from datetime import date, timedelta as _td
    from sqlalchemy import func as _sqlfunc

    today_obj = date.today()
    today_str = today_obj.isoformat()
    yesterday_str = (today_obj - _td(days=1)).isoformat()

    # 加载所有交互关系（需要判断今天是否聊过天）
    try:
        result = await db.execute(select(Interaction))
        interactions = result.scalars().all()
    except Exception as exc:
        print(f"[emotion-sched] streak load failed: {exc}")
        return

    if not interactions:
        return

    # 预加载角色，用于里程碑推送
    ai_ids = list({i.ai_id for i in interactions})
    persona_res = await db.execute(
        select(AIPersona).where(AIPersona.id.in_(ai_ids))
    )
    personas = {p.id: p for p in persona_res.scalars().all()}

    # 检查近 36h（宽一些）内有用户发出的聊天消息的 (user_id, ai_id) 组合
    cutoff = datetime.utcnow() - _td(hours=36)
    try:
        active_res = await db.execute(
            select(ChatMessage.user_id, ChatMessage.ai_id)
            .where(
                ChatMessage.role == "user",
                ChatMessage.created_at >= cutoff,
            )
            .group_by(ChatMessage.user_id, ChatMessage.ai_id)
        )
        active_pairs: set[tuple[int, int]] = {(uid, aid) for uid, aid in active_res.all()}
    except Exception as exc:
        print(f"[emotion-sched] streak active query failed: {exc}")
        return

    import json as _json
    for interaction in interactions:
        key = (interaction.user_id, interaction.ai_id)
        # 今日未互动跳过
        if key not in active_pairs:
            continue
        # 今日已计入跳过
        if interaction.last_streak_date == today_str:
            continue

        # 计算新的 streak
        if interaction.last_streak_date == yesterday_str:
            new_streak = (interaction.streak_count or 0) + 1
        else:
            new_streak = 1

        interaction.streak_count = new_streak
        interaction.last_streak_date = today_str
        interaction.total_interaction_days = (interaction.total_interaction_days or 0) + 1

        # 检查里程碑奖励
        milestone = _STREAK_MILESTONES.get(new_streak)
        if milestone is None:
            continue

        # 冷却去重：同一里程碑 24h 内不重复发放
        milestone_trigger = f"streak_milestone_{new_streak}"
        if await _check_cooldown(
            db, interaction.user_id, interaction.ai_id, "streak_milestone",
        ):
            # 也顺便写入一条里程碑专用日志，防止果动漏发
            await _log_trigger(
                db, interaction.user_id, interaction.ai_id, milestone_trigger,
            )
            continue

        # 亲密加成
        try:
            interaction.intimacy_score = float(interaction.intimacy_score or 0.0) + float(
                milestone.get("intimacy_bonus", 0)
            )
        except Exception:
            pass

        # 钻石奖励
        gems = int(milestone.get("gems", 0))
        if gems > 0:
            try:
                user_row = await db.get(User, interaction.user_id)
                if user_row is not None:
                    user_row.gem_balance = int(user_row.gem_balance or 0) + gems
                    db.add(GemTransaction(
                        user_id=interaction.user_id,
                        amount=gems,
                        balance_after=user_row.gem_balance,
                        tx_type="streak_reward",
                        reference_id=f"streak_{new_streak}_ai_{interaction.ai_id}",
                        description=f"Streak {new_streak}-day milestone reward",
                    ))
            except Exception as exc:
                print(f"[emotion-sched] streak gem grant failed: {exc}")

        # 推送消息 + 聊天记录
        persona = personas.get(interaction.ai_id)
        if persona is not None:
            msg_body = (
                f"【连续{new_streak}天里程碑】"
                f"{milestone.get('message', '')}"
            )
            db.add(ChatMessage(
                user_id=interaction.user_id,
                ai_id=interaction.ai_id,
                role="assistant",
                content=msg_body,
                message_type="proactive_dm",
                event=f"streak_{new_streak}",
                delivered=0,
            ))
            db.add(ProactiveDM(
                user_id=interaction.user_id,
                ai_id=interaction.ai_id,
                event=f"streak_{new_streak}",
                message=msg_body,
            ))
            db.add(Notification(
                user_id=interaction.user_id,
                type="streak_reward",
                title=f"连续 {new_streak} 天，{persona.name} 为你留了一条话",
                body=msg_body[:200],
                data_json=_json.dumps({
                    "ai_id": persona.id,
                    "ai_name": persona.name,
                    "streak_count": new_streak,
                    "gems": gems,
                    "intimacy_bonus": float(milestone.get("intimacy_bonus", 0)),
                }, ensure_ascii=False),
            ))

        await _log_trigger(
            db, interaction.user_id, interaction.ai_id, "streak_milestone",
        )
        await _log_trigger(
            db, interaction.user_id, interaction.ai_id, milestone_trigger,
        )
        print(
            f"[emotion-sched] streak milestone {new_streak} reached for "
            f"user={interaction.user_id} ai={interaction.ai_id}"
        )


async def process_subscription_rewards(db):
    """为订阅者发放每日钻石奖励，并清理过期订阅。"""
    from services.subscription_service import SubscriptionService

    svc = SubscriptionService()
    try:
        await svc.process_daily_rewards(db)
    except Exception as exc:
        print(f"[emotion-sched] process_daily_rewards failed: {exc}")
    try:
        await svc.check_expirations(db)
    except Exception as exc:
        print(f"[emotion-sched] check_expirations failed: {exc}")


async def run_emotion_scan():
    """
    执行一次完整的情绪状态扫描。

    扫描流程：
        1. 加载所有活跃的情绪状态（EmotionState）
        2. 预加载 AI 角色信息和用户交互数据
        3. 遍历每个情绪状态：
           a. 应用时间衰减（能量恢复、思念增长等）
           b. 获取亲密值
           c. 检查特殊状态（是否已发送欢迎消息、是否有相关记忆）
           d. 检查触发条件
           e. 对每个触发的行为执行冷却检查
           f. 执行通过冷却检查的行为
        4. 提交数据库更改

    此函数不返回值，所有操作通过数据库持久化和日志输出。
    """
    print(f"[emotion-sched] Scan starting at {datetime.now(timezone.utc).isoformat()}")

    async with async_session() as db:
        # 0. 首先处理世界事件与剧情弧阶段推进
        try:
            await process_world_events(db)
        except Exception as exc:
            print(f"[emotion-sched] process_world_events failed: {exc}")

        # 1. 加载所有情绪状态
        result = await db.execute(select(EmotionState))
        states = result.scalars().all()

        if not states:
            print("[emotion-sched] No emotion states, skipping.")
            return

        # 2. 预加载 AI 角色和交互数据（避免 N+1 查询问题）
        ai_ids = list({s.ai_id for s in states})
        persona_result = await db.execute(select(AIPersona).where(AIPersona.id.in_(ai_ids)))
        personas = {p.id: p for p in persona_result.scalars().all()}

        user_ai_pairs = [(s.user_id, s.ai_id) for s in states]
        interaction_result = await db.execute(select(Interaction))
        interactions = {
            (i.user_id, i.ai_id): i
            for i in interaction_result.scalars().all()
        }

        triggered_count = 0

        # 3. 遍历每个情绪状态进行处理
        for state in states:
            # 3a. 应用时间衰减
            emotion_engine.apply_time_decay(state)

            # 3b. 获取亲密值
            interaction = interactions.get((state.user_id, state.ai_id))
            intimacy = interaction.intimacy_score if interaction else 0.0

            # 3c. 检查是否已发送欢迎消息
            welcome_sent_result = await db.execute(
                select(EmotionTriggerLog).where(
                    EmotionTriggerLog.user_id == state.user_id,
                    EmotionTriggerLog.ai_id == state.ai_id,
                    EmotionTriggerLog.trigger_type == "welcome_dm",
                ).limit(1)
            )
            has_sent_welcome = welcome_sent_result.scalar_one_or_none() is not None

            # 3d. 检查是否有相关记忆
            from models.memory_entry import MemoryEntry
            memories_result = await db.execute(
                select(MemoryEntry).where(
                    MemoryEntry.user_id == state.user_id,
                    MemoryEntry.ai_id == state.ai_id,
                ).limit(1)
            )
            has_relevant_memory = memories_result.scalar_one_or_none() is not None

            # 3e. 检查触发条件
            triggers = emotion_engine.check_proactive_triggers(
                state, intimacy,
                has_sent_welcome=has_sent_welcome,
                has_relevant_memory=has_relevant_memory,
            )

            persona = personas.get(state.ai_id)
            if not persona:
                continue

            # 3f. 执行触发的行为
            for trigger in triggers:
                # 检查冷却时间
                if await _check_cooldown(db, state.user_id, state.ai_id, trigger):
                    continue  # 仍在冷却期，跳过

                # 获取对应的执行器
                executor = _EXECUTORS.get(trigger)
                if not executor:
                    continue

                # 执行触发行为
                try:
                    await executor(db, state, persona)
                    triggered_count += 1
                except Exception as e:
                    print(f"[emotion-sched] {trigger} failed for user={state.user_id}: {e}")

        # 提交所有数据库更改
        await db.commit()
        print(f"[emotion-sched] Scan complete. {triggered_count} triggers executed.")

        # 4. 转化触发器（变现叙事提示）
        try:
            await process_conversion_triggers(db)
            await db.commit()
        except Exception as exc:
            print(f"[emotion-sched] process_conversion_triggers failed: {exc}")

        # 5. 订阅每日奖励 + 过期清理
        try:
            await process_subscription_rewards(db)
        except Exception as exc:
            print(f"[emotion-sched] process_subscription_rewards failed: {exc}")

        # 6. 每日仪式系统（早安/晚安/心情访谈/共同习惯） (Plan Task 6)
        try:
            await process_daily_rituals(db)
            await db.commit()
        except Exception as exc:
            print(f"[emotion-sched] process_daily_rituals failed: {exc}")

        # 7. Streak 连续互动更新与里程碑奖励 (Plan Task 6)
        try:
            await process_streak_updates(db)
            await db.commit()
        except Exception as exc:
            print(f"[emotion-sched] process_streak_updates failed: {exc}")


async def run_scheduler(interval_seconds: int = CHECK_INTERVAL):
    """
    运行情绪调度器的主循环。

    初始化数据库连接后，以固定间隔持续运行情绪扫描。
    每次扫描完成后休眠指定时间，然后再次扫描。

    参数：
        interval_seconds: 扫描间隔时间（秒），默认为 CHECK_INTERVAL（30分钟）

    运行方式：
        该函数会无限循环运行，直到被中断。
    """
    await init_db()
    print(
        f"[emotion-sched] Starting emotion scheduler (interval: {interval_seconds}s)"
    )
    while True:
        try:
            await run_emotion_scan()
        except Exception as e:
            print(f"[emotion-sched] Error during scan: {e}")
            import traceback
            traceback.print_exc()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    # 作为独立脚本运行时，启动调度器
    asyncio.run(run_scheduler())