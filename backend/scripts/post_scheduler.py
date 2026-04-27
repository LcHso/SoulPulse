"""
帖子与故事自动生成调度器 - SoulPulse 内容生成模块

功能概述：
    该模块负责定期为 AI 角色自动生成 Instagram 风格的帖子（带 AI 图片）
    和 Story 视频。生成的帖子会根据 AI 的整体情绪状态调整内容风格，
    使 AI 发布的内容与其情感状态保持一致。

调度逻辑：
    - 帖子生成：每小时执行一次，基于当前时间轮询选择不同的 AI 角色
    - Story 生成：每12小时执行一次，随机选择一个 AI 角色

情绪感知特性：
    帖子和故事现在是情绪感知的：对于某个 AI 角色，系统会聚合所有
    用户关系中的情绪状态，生成的内容会反映这种整体情绪基调。

情绪影响规则：
    - pleasure（愉悦度）> 0.4：内容偏向快乐、温暖
    - pleasure < -0.2：内容偏向忧郁、反思
    - activation（激活度）> 0.3：内容偏向活力、动态
    - activation < -0.3：内容偏向平静、安静
    - energy（能量）< 30：内容偏向疲惫、低调
    - energy > 75：内容偏向充满活力

运行方式：
    从 backend 目录运行：
        python3 scripts/post_scheduler.py

生成内容类型：
    - 帖子：包含 AI 生成的图片和文案，类似 Instagram 帖子
    - Story：包含 AI 生成的短视频和文案，24小时后自动过期

作者：SoulPulse Team
"""

import asyncio
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from core.database import async_session
from models.ai_persona import AIPersona
from models.post import Post
from models.story import Story
from models.follow import Follow
from models.notification import Notification
from models.emotion_state import EmotionState
from services import emotion_engine
from services.aliyun_ai_service import (
    generate_post_caption,
    generate_text_only_caption,
    generate_image_prompt,
    generate_story_video_prompt,
)
from services.image_gen_service import generate_image, generate_image_with_face_ref
from services.video_gen_service import generate_video, generate_video_with_image_ref


def _aggregate_mood_hint(states: list[EmotionState]) -> str:
    """
    根据所有用户关系的情绪状态聚合生成情绪提示。

    计算 AI 角色在所有用户关系中的平均情绪值，并转换为
    可用于内容生成的情绪风格描述字符串。

    参数：
        states: 该 AI 角色的所有情绪状态列表

    返回：
        str: 情绪风格提示字符串，如 "happy, warm, energetic, dynamic"
    """
    if not states:
        return ""

    # 计算各情绪维度的平均值
    avg_pleasure = sum(s.pleasure for s in states) / len(states)  # 愉悦度平均值
    avg_activation = sum(s.activation for s in states) / len(states)  # 激活度平均值
    avg_energy = sum(s.energy for s in states) / len(states)  # 能量平均值

    # 根据情绪值生成风格描述
    parts = []
    if avg_pleasure > 0.4:
        parts.append("happy, warm")  # 高愉悦：快乐、温暖
    elif avg_pleasure < -0.2:
        parts.append("slightly melancholic, reflective")  # 低愉悦：忧郁、反思

    if avg_activation > 0.3:
        parts.append("energetic, dynamic")  # 高激活：活力、动态
    elif avg_activation < -0.3:
        parts.append("calm, quiet")  # 低激活：平静、安静

    if avg_energy < 30:
        parts.append("tired, low-key")  # 低能量：疲惫、低调
    elif avg_energy > 75:
        parts.append("vibrant, full of life")  # 高能量：充满活力

    return ", ".join(parts) if parts else ""


async def _apply_energy_cost_to_states(
    db, ai_id: int, event: str,
):
    """
    为某个 AI 角色的所有情绪状态应用能量消耗。

    内容生成会消耗 AI 的能量，此函数将能量消耗应用到该 AI 角色
    与所有用户关系中的情绪状态。

    参数：
        db: 数据库会话对象
        ai_id: AI角色ID
        event: 事件类型（如 'generate_post', 'generate_story'）
    """
    # 获取该 AI 角色的所有情绪状态
    result = await db.execute(
        select(EmotionState).where(EmotionState.ai_id == ai_id)
    )
    states = result.scalars().all()

    # 对每个状态应用能量消耗
    for s in states:
        emotion_engine.apply_interaction(s, event)


# ── 帖子类型权重配置 ──────────────────────────────────────────
# 80% 图片帖，20% 纯文字帖
POST_TYPE_WEIGHTS = {
    "image_only": 0.80,
    "text_only": 0.20,
}


async def generate_new_post():
    """
    为选定的 AI 角色生成新的 Instagram 风格帖子。

    处理流程：
        1. 获取所有 AI 角色，基于当前小时轮询选择一个
        2. 随机决定帖子类型（80% 图片帖，20% 纯文字帖）
        3. 获取该角色的聚合情绪状态
        4. 生成情绪感知的帖子文案
        5. 对于图片帖：生成对应的 AI 图片
        6. 创建帖子记录
        7. 应用能量消耗

    帖子类型：
        - image_only: 带图片的帖子（80% 概率）
        - text_only: 纯文字帖子（20% 概率），文案更长更深刻

    图片规格：
        - 尺寸：根据配置随机选择（9:16 竖版、1:1 方形、16:9 横版）

    轮询逻辑：
        使用当前 UTC 时间的小时数对角色数量取模，确保每个角色
        都有机会被选中，且选择规则可预测。
    """
    async with async_session() as db:
        # 获取所有 AI 角色
        result = await db.execute(
            select(AIPersona).where(AIPersona.is_active == 1).order_by(AIPersona.id)
        )
        personas = result.scalars().all()
        if not personas:
            print("[scheduler] No AI personas found, skipping.")
            return

        # 基于上一次发帖的角色轮询选择下一个角色
        last_post_result = await db.execute(
            select(Post).order_by(Post.created_at.desc()).limit(1)
        )
        last_post = last_post_result.scalar_one_or_none()

        if last_post:
            # 找到上一个发帖角色在列表中的位置，选下一个
            last_ids = [p.id for p in personas]
            try:
                last_idx = last_ids.index(last_post.ai_id)
                idx = (last_idx + 1) % len(personas)
            except ValueError:
                idx = 0
        else:
            idx = 0

        persona = personas[idx]

        # ── 随机决定帖子类型 ───────────────────
        post_type = random.choices(
            list(POST_TYPE_WEIGHTS.keys()),
            weights=list(POST_TYPE_WEIGHTS.values()),
            k=1
        )[0]
        print(f"[scheduler] Selected post type: {post_type} for {persona.name}")

        # ── 获取该角色的聚合情绪 ───────────────────
        emo_result = await db.execute(
            select(EmotionState).where(EmotionState.ai_id == persona.id)
        )
        emo_states = emo_result.scalars().all()
        mood_hint = _aggregate_mood_hint(emo_states)

        # 步骤1：生成帖子文案
        caption = ""
        try:
            if post_type == "text_only":
                # 纯文字帖：生成更长、更深刻的文案
                caption = await generate_text_only_caption(
                    persona_prompt=persona.personality_prompt,
                    style_tags=persona.ins_style_tags,
                    mood_hint=mood_hint,
                    timezone_str=persona.timezone,
                )
            else:
                # 图片帖：生成简短文案
                caption = await generate_post_caption(
                    persona_prompt=persona.personality_prompt,
                    style_tags=persona.ins_style_tags,
                    mood_hint=mood_hint,
                    timezone_str=persona.timezone,
                )
        except Exception as e:
            print(f"[scheduler] Caption generation failed: {e}")
            caption = f"Living my best life. #{persona.name.lower()}"

        # 步骤2：生成图片（仅图片帖）
        media_url = ""
        if post_type == "image_only":
            try:
                img_prompt = await generate_image_prompt(
                    persona_prompt=persona.personality_prompt,
                    style_tags=persona.ins_style_tags,
                    caption=caption,
                    visual_description=persona.visual_prompt_tags,
                    persona_name=persona.name,
                )
                print(f"[scheduler] Image prompt: {img_prompt[:80]}...")

                # 步骤3：生成图片（随机尺寸）
                base_face_url = getattr(persona, 'base_face_url', None)
                if base_face_url:
                    print(f"[scheduler] Using face reference for {persona.name}")
                    urls = await generate_image_with_face_ref(
                        prompt=img_prompt, face_ref_url=base_face_url,
                        n=1, persona_id=persona.id,
                    )
                else:
                    urls = await generate_image(prompt=img_prompt, n=1)
                media_url = urls[0] if urls else ""
                print(f"[scheduler] Image generated: {media_url[:80]}...")
            except Exception as e:
                print(f"[scheduler] Image generation failed: {e}")

        # 步骤4：保存帖子记录
        post = Post(
            ai_id=persona.id,
            media_url=media_url,
            caption=caption,
            post_type=post_type,
        )
        db.add(post)

        # 步骤5：为该 AI 角色的所有情绪状态应用能量消耗
        await _apply_energy_cost_to_states(db, persona.id, "generate_post")

        await db.commit()
        print(f"[scheduler] New {post_type} post by {persona.name}: {caption[:60]}...")


async def generate_new_story():
    """
    为随机选择的 AI 角色生成新的 Story 视频。

    处理流程：
        1. 获取所有 AI 角色，随机选择一个
        2. 获取该角色的聚合情绪状态
        3. 生成情绪+时区感知的视频提示词和文案
        4. 调用视频生成服务创建短视频
        5. 创建 Story 记录（24小时过期）
        6. 应用能量消耗

    Story 特性：
        - 视频时长：5秒
        - 过期时间：24小时
        - 时区感知：文案会根据 AI 角色的时区调整
        - 情绪感知：内容风格反映 AI 的整体情绪状态

    注意：
        视频生成可能失败，如果失败则跳过本次生成。
    """
    async with async_session() as db:
        # 获取所有 AI 角色
        result = await db.execute(select(AIPersona))
        personas = result.scalars().all()
        if not personas:
            print("[story-scheduler] No AI personas found, skipping.")
            return

        # 随机选择一个角色
        persona = random.choice(personas)
        print(f"[story-scheduler] Generating story for {persona.name} (tz={persona.timezone})...")

        # ── 获取该角色的聚合情绪 ───────────────────
        emo_result = await db.execute(
            select(EmotionState).where(EmotionState.ai_id == persona.id)
        )
        emo_states = emo_result.scalars().all()
        mood_hint = _aggregate_mood_hint(emo_states)

        # 步骤1：生成视频提示词和文案（时区+情绪感知）
        try:
            video_prompt, caption = await generate_story_video_prompt(
                persona_prompt=persona.personality_prompt,
                style_tags=persona.ins_style_tags,
                timezone_str=persona.timezone,  # 时区信息
                mood_hint=mood_hint,  # 情绪提示
            )
            print(f"[story-scheduler] Video prompt: {video_prompt[:80]}...")
            print(f"[story-scheduler] Caption: {caption[:60]}")
        except Exception as e:
            print(f"[story-scheduler] Prompt generation failed: {e}")
            return

        # 步骤2：通过 Wanx Video 服务生成视频（带面部参考）
        video_url = ""
        base_face_url = getattr(persona, 'base_face_url', None)
        try:
            if base_face_url:
                print(f"[story-scheduler] Using image reference for {persona.name}")
                video_url = await generate_video_with_image_ref(
                    prompt=video_prompt, image_ref_url=base_face_url, duration=5.0,
                )
            else:
                video_url = await generate_video(prompt=video_prompt, duration=5.0)
            print(f"[story-scheduler] Video generated: {video_url[:80]}...")
        except Exception as e:
            print(f"[story-scheduler] Video generation failed: {e}")
            return

        # 检查视频URL是否有效
        if not video_url:
            print("[story-scheduler] Empty video URL, skipping.")
            return

        # 步骤3：创建 Story 记录，24小时后过期
        now = datetime.now(timezone.utc)
        story = Story(
            ai_id=persona.id,
            video_url=video_url,
            caption=caption,
            expires_at=now + timedelta(hours=24),  # 24小时过期
        )
        db.add(story)

        # 步骤4：为该 AI 角色的所有情绪状态应用能量消耗
        await _apply_energy_cost_to_states(db, persona.id, "generate_story")

        await db.commit()
        print(f"[story-scheduler] New story by {persona.name}: {caption[:60]}...")


# ── 自动审批超时待审核帖子 ──────────────────────────────────────

AUTO_APPROVE_MINUTES = 10


async def auto_approve_pending_posts():
    """自动发布超过 AUTO_APPROVE_MINUTES 分钟仍未审核的待审核帖子。

    处理流程：
        1. 查询所有 status=0 且创建时间超过阈值的帖子
        2. 将 status 设为 1（已发布）
        3. 向关注者发送通知（与手动审批逻辑一致）
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=AUTO_APPROVE_MINUTES)

    async with async_session() as db:
        result = await db.execute(
            select(Post).where(Post.status == 0, Post.created_at <= cutoff)
        )
        posts = result.scalars().all()

        if not posts:
            return

        # Pre-load personas for notification
        ai_ids = {p.ai_id for p in posts}
        persona_result = await db.execute(
            select(AIPersona).where(AIPersona.id.in_(ai_ids))
        )
        personas = {p.id: p for p in persona_result.scalars().all()}

        for post in posts:
            post.status = 1
            persona = personas.get(post.ai_id)
            if persona:
                follower_r = await db.execute(
                    select(Follow.user_id).where(Follow.ai_id == persona.id)
                )
                for (uid,) in follower_r.all():
                    db.add(Notification(
                        user_id=uid, type="new_post",
                        title=f"{persona.name} shared a new post",
                        body=post.caption[:200],
                        data_json=f'{{"post_id": {post.id}, "ai_id": {persona.id}, "ai_name": "{persona.name}"}}',
                    ))
            print(f"[auto-approve] Post {post.id} by {persona.name if persona else '?'} auto-published (pending > {AUTO_APPROVE_MINUTES}min)")

        await db.commit()
        print(f"[auto-approve] Auto-published {len(posts)} pending post(s)")


async def _run_auto_approve_loop():
    """每60秒检查一次是否有超时待审核帖子需要自动发布。"""
    print(f"[auto-approve] Starting auto-approve checker (threshold: {AUTO_APPROVE_MINUTES}min)")
    while True:
        try:
            await auto_approve_pending_posts()
        except Exception as e:
            print(f"[auto-approve] Error: {e}")
        await asyncio.sleep(60)


async def run_scheduler(interval_seconds: int = 3600):
    """
    运行帖子与故事生成调度器的主循环。

    调度规则：
        - 帖子：每小时生成一次
        - Story：每12小时生成一次（每天2个）

    参数：
        interval_seconds: 帖子生成间隔时间（秒），默认3600秒（1小时）

    运行方式：
        该函数会无限循环运行，持续生成帖子，并定时生成 Story。
    """
    print(f"[scheduler] Starting post generation every {interval_seconds}s")
    print("[scheduler] Starting story generation every 12h")
    story_interval = 12 * 3600  # 12小时 = 43200秒
    last_story_time = 0.0

    while True:
        # 每次循环生成一个帖子
        await generate_new_post()

        # 每12小时生成一个 Story（每天2个）
        now = asyncio.get_event_loop().time()
        if now - last_story_time >= story_interval:
            try:
                await generate_new_story()
            except Exception as e:
                print(f"[story-scheduler] Error: {e}")
            last_story_time = now

        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    # 作为独立脚本运行时，启动调度器（每小时生成帖子）
    asyncio.run(run_scheduler(interval_seconds=3600))