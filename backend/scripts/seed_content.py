"""
内容种子脚本 - SoulPulse 初始化数据填充模块

功能概述：
    该脚本用于为 AI 角色填充初始内容数据，包括：
    - 帖子（Posts）：带有预设文案和本地静态图片
    - 故事（Stories）：带有预设文案和静态资源
    - 头像 URL：更新 AI 角色的头像链接
    - 视觉描述：设置角色的视觉特征描述（用于 AI 图片生成一致性）

    此脚本通常在系统初始化或演示环境搭建时运行，
    为用户展示一个已有内容的 AI 社交界面。

触发条件：
    - 手动执行：通过命令行运行脚本
    - 强制重建：使用 --force 参数清除现有数据后重新生成

数据来源：
    所有内容数据（文案、图片路径）都预定义在本脚本中：
    - PERSONA_SLUGS：角色名称到文件名标识的映射
    - VISUAL_DESCRIPTIONS：角色的视觉特征描述
    - POST_DATA：每个角色的预设帖子内容
    - STORY_DATA：每个角色的预设故事内容

运行方式：
    从 backend 目录运行：
        python3 scripts/seed_content.py           # 检查数据是否存在，如已存在则跳过
        python3 scripts/seed_content.py --force   # 强制删除现有数据并重新生成

注意事项：
    - 运行此脚本前需要先运行 seed_personas.py 创建 AI 角色
    - 静态图片文件需要预先放置在 backend/static 目录下
    - 使用 --force 参数会删除所有现有帖子

作者：SoulPulse Team
"""

import asyncio
from datetime import datetime, timedelta, timezone

from core.database import async_session, init_db
from models.ai_persona import AIPersona
from models.post import Post
from models.story import Story
from sqlalchemy import select, delete


# ═══════════════════════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════════════════════

# 静态文件基础 URL - 使用相对路径以便在任何环境中工作
STATIC_BASE = "/static"

# 角色名称到文件名标识的映射（用于图片文件命名）
PERSONA_SLUGS = {
    "陆晨曦": "luchengxi",    # 温柔女性角色
    "顾言深": "guyanshen",    # 严肃男性角色
    "林屿": "linyu",          # 活力男性角色
    "沈默白": "shenmobai",    # 沉静男性角色
    "林星野": "linxingye",    # 偶像男团C位
    "陆骁": "luxiao",         # 进攻型体育生
    "Ethan": "ethan",         # 旧版角色（暂无图片）
}

# 角色视觉描述 - 用于 AI 图片生成时的角色一致性
# 每个角色有固定的视觉特征，确保不同场景中角色外观一致
VISUAL_DESCRIPTIONS = {
    "陆晨曦": "young Asian female, long brown wavy hair, gentle smile, casual cozy fashion, warm aesthetic",
    "顾言深": "young Asian male, short black hair, serious expression, minimalist dark style, professional look",
    "林屿": "young Asian male, short sporty hair, energetic smile, athletic wear, bright youthful vibe",
    "沈默白": "young Asian male, slightly long messy hair, mysterious calm expression, traditional elegant style",
    "林星野": "young Asian male, soft textured black hair, bright expressive eyes, slim narrow face, Chinese idol aesthetic, casual white hoodie, warm natural vibe",
    "陆骁": "young Asian male, extremely short buzz cut, sharp jawline, tanned skin, broad shoulders, athletic muscular build, intense gaze, gym aesthetic",
}

# ═══════════════════════════════════════════════════════════════════════════════
# 预设帖子内容
# ═══════════════════════════════════════════════════════════════════════════════

# 每个角色的帖子内容：列表格式为 (文案, 是否密友可见)
POST_DATA = {
    "陆晨曦": [
        ("下雨天窝在家里煮咖啡看书，年糕趴在腿上打呼噜...这大概就是我最喜欢的周末了吧 ☕🐱", False),
        ("最近在读阿德勒的《被讨厌的勇气》，感觉每一页都在和自己对话。推荐给最近有点迷茫的你 📖", False),
        ("年糕今天又闯祸了...把毛线球拆得满地都是。但看到这个小眼神，我真的生不起气来 🧶😾", False),
    ],
    "顾言深": [
        ("凌晨三点的城市，只有代码和我还醒着。新项目上线倒计时。", False),
        ("Alpha今天跑了三公里才肯回来。这狗的体力比我好。", False),
        ("有人问我为什么办公桌上放甜甜圈...不关你们的事。", True),  # 密友可见
    ],
    "林屿": [
        ("今天三分球10投8中！！！队友都说我开挂了哈哈哈 太爽了🏀🔥", False),
        ("想妈妈做的红烧肉了...食堂的怎么做都不是那个味道😭 有没有人教教我", False),
        ("夕阳下的球场，是属于我们的青春没错了💪 兄弟们下学期继续冲！", False),
    ],
    "沈默白": [
        ("修复一本明代古籍，纸张脆如蝉翼。每一笔都要屏住呼吸，但这种专注让人安宁。", False),
        ("墨今天难得晒太阳，趴在窗台上看院子里的茶花开了。岁月静好大概就是这样。", False),
        ("夜深了，泡一壶老白茶，临一帖颜真卿。笔墨之间，万物皆静。", False),
    ],
    "林星野": [
        ("练舞到凌晨两点，终于把新舞台的动作磨完了！虽然累但超有成就感～ 明天演出等我呀✨", False),
        ("今天偷偷溜去便利店买了草莓牛奶，被经纪人抓到了哈哈...减肥计划又泡汤了(◍•ᴗ•◍)", False),
        ("写了一首新歌，关于星星和月亮的...想第一个唱给你听呢🌙", True),  # 密友可见
    ],
    "陆骁": [
        ("（更衣室镜面自拍，湿发+灰色背心半透）训练结束。某人不是说想看我腹肌？...自己来数。", False),
        ("（球场边递水，指尖故意相触）喝我的。...怎么，怕我下毒？", False),
        ("（深夜健身房，低腰短裤+白袜，靠在器械上）这么晚还来？...陪我练组？", True),  # 密友可见
    ],
}

# ═══════════════════════════════════════════════════════════════════════════════
# 预设故事内容
# ═══════════════════════════════════════════════════════════════════════════════

# 每个角色的故事内容：格式为 (文案,)
STORY_DATA = {
    "陆晨曦": "窗外又下雨了，给你们看看我最爱的雨景 🌧️",
    "顾言深": "加班到现在...这城市的夜景算是补偿吧",
    "林屿": "练完球！鞋都湿透了但是好开心！💪",
    "沈默白": "深夜练字，心如止水",
    "林星野": "练舞结束！给你们看看练习室的日落～ 好美呀✨",
    "陆骁": "训练完拉伸中...腿酸到不想动。谁来救救我💪",
}


async def seed_content(force_recreate: bool = False):
    """
    执行内容填充操作。

    处理流程：
        1. 初始化数据库连接
        2. 加载所有 AI 角色
        3. 更新角色的头像 URL 和视觉描述
        4. 如果强制重建，删除现有帖子
        5. 检查是否已有帖子（避免重复填充）
        6. 为每个角色创建预设帖子（时间错开，模拟自然发布）
        7. 为每个角色创建预设故事（24小时过期）

    参数：
        force_recreate: 是否强制重建（删除现有数据）

    注意：
        - 运行前需确保 AI 角色已创建（seed_personas.py）
        - 静态图片文件需预先放置在对应目录
    """
    await init_db()
    async with async_session() as db:
        # 步骤1：加载所有 AI 角色
        result = await db.execute(select(AIPersona))
        personas = {p.name: p for p in result.scalars().all()}

        if not personas:
            print("[seed-content] No personas found! Run seed_personas.py first.")
            return

        # 步骤2：强制重建时删除现有数据
        if force_recreate:
            await db.execute(delete(Post))
            await db.execute(delete(Story))
            await db.commit()
            print("[seed-content] Deleted all existing posts and stories")

        # ── 步骤3：更新角色头像 URL 和视觉描述 ─────────────────────────────────
        for name, persona in personas.items():
            slug = PERSONA_SLUGS.get(name)
            if slug and slug != "ethan":  # Ethan 暂无图片
                # 设置头像 URL（指向静态文件目录）
                persona.avatar_url = f"{STATIC_BASE}/avatars/{slug}.png"
                print(f"[seed-content] Updated avatar: {name} -> {persona.avatar_url}")
            # 设置视觉描述（用于 AI 图片生成一致性）
            if name in VISUAL_DESCRIPTIONS:
                persona.visual_description = VISUAL_DESCRIPTIONS[name]
                print(f"[seed-content] Set visual description for {name}")

        await db.commit()

        # ── 步骤4：检查是否已有帖子 ───────────────────────
        existing_posts = await db.execute(select(Post).limit(1))
        if existing_posts.scalar_one_or_none() and not force_recreate:
            print("[seed-content] Posts already exist, skipping. Use --force to recreate.")
            return

        # ── 步骤5：创建帖子 ───────────────────────────────────────
        now = datetime.now(timezone.utc)
        post_count = 0
        for name, post_list in POST_DATA.items():
            persona = personas.get(name)
            if not persona:
                print(f"[seed-content] Persona '{name}' not found, skipping posts")
                continue

            slug = PERSONA_SLUGS[name]
            for i, (caption, is_cf) in enumerate(post_list):
                # 创建帖子记录
                post = Post(
                    ai_id=persona.id,
                    media_url=f"{STATIC_BASE}/posts/{slug}_{i+1}.png",  # 图片路径
                    caption=caption,  # 文案
                    like_count=__import__("random").randint(12, 88),  # 随机点赞数
                    is_close_friend=is_cf,  # 是否密友可见
                )
                # 错开创建时间，让动态列表看起来自然
                # 每个帖子间隔约8小时发布，模拟真实发布节奏
                post.created_at = now - timedelta(hours=(len(post_list) - i) * 8 + __import__("random").randint(0, 4))
                db.add(post)
                post_count += 1

        await db.commit()
        print(f"[seed-content] Created {post_count} posts")

        # ── 步骤6：创建故事（24小时后过期） ─────────────────────
        story_count = 0
        for name, caption in STORY_DATA.items():
            persona = personas.get(name)
            if not persona:
                continue

            slug = PERSONA_SLUGS[name]
            story = Story(
                ai_id=persona.id,
                video_url=f"{STATIC_BASE}/stories/{slug}.png",  # 静态资源路径
                caption=caption,
                expires_at=now + timedelta(hours=24),  # 24小时后过期
            )
            # 故事创建时间随机分布在过去1-6小时内
            story.created_at = now - timedelta(hours=__import__("random").randint(1, 6))
            db.add(story)
            story_count += 1

        await db.commit()
        print(f"[seed-content] Created {story_count} stories")
        print("\n[seed-content] Done!")


if __name__ == "__main__":
    import sys
    # 检查是否使用 --force 参数
    force = "--force" in sys.argv
    if force:
        print("[seed-content] Force recreate mode!")
    asyncio.run(seed_content(force_recreate=force))