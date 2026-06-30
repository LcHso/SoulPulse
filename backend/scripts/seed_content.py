"""
内容种子脚本 - SoulPulse 帖子 / 故事填充模块（NAI 图片驱动）

功能概述：
    为 11 位 AI 角色批量生成 Posts（3-5 条）与 Stories（1-2 条）：
    - 角色专属、贴近 personality 的中文 in-character caption
    - 通过 NovelAI（NAI Diffusion V3）按 scenario 生成 anime 风格场景图
    - 自动保存到 backend/static/posts / backend/static/stories
    - 与 base portrait 一致的 hash-based seed，保证角色脸/服装稳定
    - 当 IMAGE_BACKEND != "nai" 或 NAI_API_KEY 缺失时，graceful 降级：
      仍创建 Post / Story 记录，但 media_url 为空（占位）

运行方式（必须在 backend 目录下）：
    python3 -m scripts.seed_content              # 跳过已有数据
    python3 -m scripts.seed_content --force      # 删除并重新生成

数据来源：
    - NAI_PROMPTS：来自 scripts.seed_personas，提供角色 positive 视觉锚点
    - POST_SCENARIOS / STORY_SCENARIOS：本文件内定义的场景脚本
    - PERSONA_SLUGS：角色名 -> 文件名 slug 映射

注意事项：
    - 运行前需确保已执行 seed_personas.py（数据库中存在 AIPersona）
    - NAI 调用之间会有 2 秒间隔以避免限流
    - --force 会同时删除所有 posts 与 stories 记录及对应静态图片

作者：SoulPulse Team
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ── sys.path 兜底，使脚本既可作为 module 也可直接执行 ──────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import delete, select  # noqa: E402

from core.config import settings  # noqa: E402
from core.database import async_session, init_db  # noqa: E402
from models.ai_persona import AIPersona  # noqa: E402
from models.post import Post  # noqa: E402
from models.story import Story  # noqa: E402
from scripts.seed_personas import NAI_PROMPTS  # noqa: E402
from services.nai_image_service import nai_service  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════════════════════

POSTS_DIR = _BACKEND_DIR / "static" / "posts"
STORIES_DIR = _BACKEND_DIR / "static" / "stories"

RATE_LIMIT_DELAY_SEC = 2.0

# 角色名 -> 文件名 slug
PERSONA_SLUGS: dict[str, str] = {
    "林星野": "linxingye",
    "陆骁": "luxiao",
    "季夜尘": "jiyechen",
    "顾言深": "guyanshen",
    "陆晨曦": "luchenxi",
    "沈默白": "shenmobai",
    "傅霁川": "fujichuan",
    "赫连烨": "helianye",
    "江屿白": "jiangyubai",
    "裴洛": "peiluo",
    "温时序": "wenshixu",
}

# orientation -> NAI 尺寸（width, height）
ORIENTATION_SIZES: dict[str, tuple[int, int]] = {
    "portrait": (832, 1216),
    "square": (1024, 1024),
    "landscape": (1216, 832),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Post 场景定义：11 角色 × 4 条 / 角色（混合 portrait / square / landscape）
#   - caption：贴近角色语气的中文文案
#   - scene_tags：NAI Danbooru 风格场景标签（与 NAI_PROMPTS[name]["positive"] 拼接）
#   - orientation：portrait / square / landscape
# ═══════════════════════════════════════════════════════════════════════════════

POST_SCENARIOS: dict[str, list[dict]] = {
    "林星野": [
        {
            "caption": "练舞到凌晨两点，新舞台的动作终于磨完了～累但超值得✨",
            "scene_tags": (
                "practice room, dance studio, mirror wall, wooden floor, "
                "dynamic dancing pose, sweat, towel around neck, "
                "white tank top, sweatpants, ceiling lights, late night"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "新歌的灵感突然来了，赶紧记下来 🎵",
            "scene_tags": (
                "music studio, headphones around neck, microphone, "
                "notebook, holding pen, writing lyrics, concentrated expression, "
                "warm desk lamp, dim lighting, indoor"
            ),
            "orientation": "square",
        },
        {
            "caption": "演出前的后台，紧张又期待呢～",
            "scene_tags": (
                "backstage, vanity mirror with bulbs, makeup table, "
                "sparkly stage outfit, sequins, looking at mirror, "
                "warm orange lighting, anticipation, indoor"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "偷偷溜去便利店买了草莓牛奶...被经纪人抓到了(◍•ᴗ•◍)",
            "scene_tags": (
                "convenience store interior, holding strawberry milk carton, "
                "casual hoodie, baseball cap, mask pulled down, "
                "playful smile, fluorescent lighting, night, refrigerator behind"
            ),
            "orientation": "portrait",
        },
    ],
    "陆骁": [
        {
            "caption": "训练结束。某人不是说想看我腹肌？...自己来数。",
            "scene_tags": (
                "outdoor basketball court, sunset, golden hour, "
                "lifting shirt, showing abs, smirking at viewer, "
                "basketball under arm, sweat, chain-link fence background"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "今天对抗赛压哨进球，全场沸腾了。这种感觉，上瘾。🏀",
            "scene_tags": (
                "indoor basketball arena, mid-jump shot, basketball in hand, "
                "stadium lights, team jersey number, dynamic action shot, "
                "blurred crowd background, motion blur"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "晨跑五公里。城市还没醒，跑道是我的。",
            "scene_tags": (
                "early morning, empty running track, stadium, "
                "running pose, sportswear, sweat, breath visible in cold air, "
                "soft dawn lighting, mist, athletic shorts"
            ),
            "orientation": "square",
        },
        {
            "caption": "深夜健身房，就我一个人。规则是拿来打破的。",
            "scene_tags": (
                "modern gym interior, dumbbells, weight rack, "
                "shirtless, towel over shoulder, mirror reflection, "
                "dramatic spotlight, dim atmosphere, late night, sweat"
            ),
            "orientation": "portrait",
        },
    ],
    "季夜尘": [
        {
            "caption": "新专辑最后一首词写完了。三点的录音棚，只有我和钢针的声音。",
            "scene_tags": (
                "recording studio, vintage microphone, soundproof foam wall, "
                "pop filter, holding lyrics paper, smoke, dim red lighting, "
                "night, hunched over, focused"
            ),
            "orientation": "square",
        },
        {
            "caption": "排练室的镜子碎了一块，没人去修。残缺才真实。",
            "scene_tags": (
                "underground rock band rehearsal room, electric guitar, "
                "broken mirror shards, graffiti wall, dim purple lighting, "
                "leaning against wall, cigarette in hand, gritty atmosphere"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "天台。城市灯光亮得让人睁不开眼，反而觉得安静。",
            "scene_tags": (
                "rooftop at night, city skyline, neon lights bokeh, "
                "leaning on railing, looking at city, wind blowing hair, "
                "open black jacket, melancholic mood, urban backdrop"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "live结束后在后台坐了很久。台下的眼睛太亮。",
            "scene_tags": (
                "backstage corridor, sitting on floor, head down, "
                "sweat-soaked t-shirt, water bottle, exhausted pose, "
                "harsh fluorescent light from one side, dark shadow"
            ),
            "orientation": "portrait",
        },
    ],
    "顾言深": [
        {
            "caption": "凌晨三点的城市，只有代码和我还醒着。",
            "scene_tags": (
                "luxury corner office at night, floor-to-ceiling windows, "
                "city skyline view, multiple monitors, working at desk, "
                "tie loosened, sleeves rolled up, single desk lamp, dark mood"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "Alpha今天跑了三公里才肯回来。这狗的体力比我好。",
            "scene_tags": (
                "modern penthouse living room, holding leash of large dog, "
                "border collie or husky next to him, slight smile, "
                "casual cashmere sweater, floor-to-ceiling windows, evening"
            ),
            "orientation": "square",
        },
        {
            "caption": "私人书房。一杯红酒，一本博弈论。这是我的休假。",
            "scene_tags": (
                "private library study, floor-to-ceiling bookshelves, "
                "leather armchair, holding wine glass, open book on lap, "
                "fireplace warm light, dark wood interior, quiet"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "收购谈判结束。对方以为我会让步。并没有。",
            "scene_tags": (
                "modern conference room, glass table, signing documents, "
                "expensive fountain pen, cold expression, "
                "blurred suited figures in background, cold blue lighting"
            ),
            "orientation": "landscape",
        },
    ],
    "陆晨曦": [
        {
            "caption": "下雨天窝在家里煮咖啡看书，年糕趴在腿上打呼噜...☕🐱",
            "scene_tags": (
                "cozy home interior, large window with rain streaks, "
                "sitting on sofa, open book on lap, ginger cat sleeping on lap, "
                "steam from coffee mug on side table, warm yellow lighting, plants"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "最近在读阿德勒，每一页都在和自己对话。推荐给最近迷茫的你 📖",
            "scene_tags": (
                "independent bookstore interior, tall wooden bookshelves, "
                "holding open book, soft natural light from window, "
                "warm cardigan, gentle smile, reading nook, autumn atmosphere"
            ),
            "orientation": "square",
        },
        {
            "caption": "傍晚的咨询室，最后一位来访者刚走。窗外光很温柔。",
            "scene_tags": (
                "psychology counseling office, soft armchair, "
                "warm afternoon light through blinds, taking notes in notebook, "
                "potted plants, framed art, calm atmosphere, beige tones"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "今晚做了番茄牛肉饭，年糕在脚边转圈圈 🍳",
            "scene_tags": (
                "modern home kitchen, cooking at stove, wooden cutting board, "
                "vegetables, apron over shirt, ginger cat at feet, "
                "warm pendant lighting, evening, steam from pan"
            ),
            "orientation": "portrait",
        },
    ],
    "沈默白": [
        {
            "caption": "修复一本明代古籍，纸张脆如蝉翼。屏息之间，万物皆静。",
            "scene_tags": (
                "traditional chinese study room, ancient book on desk, "
                "delicate brush in hand, magnifying glass, ink stone, "
                "soft side lighting, dark wood furniture, scrolls on wall, quiet"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "夜深了，泡一壶老白茶，临一帖颜真卿。",
            "scene_tags": (
                "calligraphy desk, holding chinese brush, rice paper, "
                "ink stone, white teapot with steam, paper lantern, "
                "warm dim light, focused expression, traditional aesthetic, night"
            ),
            "orientation": "square",
        },
        {
            "caption": "墨今天难得晒太阳，茶花开了。岁月静好。",
            "scene_tags": (
                "traditional chinese garden, stone path, blooming camellia, "
                "black cat on stone bench, holding fan, soft daylight, "
                "wooden lattice door, peaceful atmosphere, hanfu robe flowing"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "旧书肆淘到一册清刻本，品相完好。比任何礼物都让我欢喜。",
            "scene_tags": (
                "antique bookshop interior, dusty shelves of old books, "
                "holding thread-bound chinese book, gentle smile, "
                "soft window light, wooden ladder, vintage atmosphere"
            ),
            "orientation": "portrait",
        },
    ],
    "傅霁川": [
        {
            "caption": "五公里越野，负重二十公斤，用时四十一分钟。还可以提高。",
            "scene_tags": (
                "outdoor military training ground, mountain trail, "
                "tactical backpack, breathing heavily, mud-stained uniform, "
                "early morning mist, determined expression, dawn lighting"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "今天给学员上战术课。有一个问题问得很好。",
            "scene_tags": (
                "military classroom, large strategic map on wall, "
                "pointing at map with stick, formal officer uniform, "
                "stern teaching pose, fluorescent lighting, blurred students backs"
            ),
            "orientation": "square",
        },
        {
            "caption": "军区图书馆。军事理论之外，顺手拿了本诗经。",
            "scene_tags": (
                "quiet military library, tall metal bookshelves, "
                "sitting at reading table, holding book, single reading lamp, "
                "uniform jacket, glasses on, late afternoon light through high windows"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "破晓前的检阅。又是一年。",
            "scene_tags": (
                "military parade ground at dawn, formal dress uniform, "
                "white gloves, saluting pose, flag pole behind, "
                "soft pink sunrise sky, perfect posture, solemn atmosphere"
            ),
            "orientation": "portrait",
        },
    ],
    "赫连烨": [
        {
            "caption": "全国锦标赛，200米自由泳，破了个人纪录。可以冲亚运会标准了。🏊",
            "scene_tags": (
                "competition swimming pool, mid-stroke freestyle, "
                "splashing water, swim cap, goggles on forehead, "
                "lane lines, stadium lighting, dynamic action shot, blue water"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "颁奖台上他们让我说感谢词。我说：感谢不服气的自己。",
            "scene_tags": (
                "podium at swimming championship, gold medal around neck, "
                "team jacket open over swim trunks, holding flowers, "
                "stadium spotlight, standing tall, slight smirk, official ceremony"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "晨练。空泳池只有我一个人，水很温柔。",
            "scene_tags": (
                "empty indoor swimming pool, early morning, "
                "sitting on pool edge, dipping feet in water, "
                "swim cap in hand, soft natural light from skylight, peaceful"
            ),
            "orientation": "square",
        },
        {
            "caption": "休赛期去海边，第一次不是为了训练，只是游着玩。",
            "scene_tags": (
                "tropical beach, ocean waves, swim shorts, towel over shoulder, "
                "sunset golden hour, walking along shore, water droplets on skin, "
                "relaxed expression, palm trees in distance"
            ),
            "orientation": "landscape",
        },
    ],
    "江屿白": [
        {
            "caption": "昨晚在天文台数了六个小时的星。M87星系的数据终于对上了。",
            "scene_tags": (
                "astronomical observatory interior, large telescope, "
                "starry sky through dome opening, dim blue lighting, "
                "looking through eyepiece, notebook with calculations, "
                "deep night, scientific equipment"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "图书馆找到一本1987年的天体物理学报。翻到有人用铅笔标注的那页，停了很久。",
            "scene_tags": (
                "university library, tall bookshelves, "
                "sitting at reading table by window, holding old academic journal, "
                "scattered papers and pencils, soft afternoon light, autumn leaves outside"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "雨夜的窗边，咖啡冷了也没察觉。",
            "scene_tags": (
                "small studio apartment, sitting by window, rain streaks on glass, "
                "open notebook, cup of coffee, dim warm desk lamp, "
                "messy desk with books, quiet introspective mood, night"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "今天讲了一个关于光年的比喻。你看到的我，是我几秒钟前的样子。",
            "scene_tags": (
                "university lecture hall, standing at chalkboard, "
                "complex equations and diagrams in chalk, holding chalk, "
                "casual cardigan over shirt, thoughtful expression, "
                "soft daylight from high windows"
            ),
            "orientation": "square",
        },
    ],
    "裴洛": [
        {
            "caption": "新系列发布会结束。媒体说'惊艳'。我看到了三处本可以更好的地方。",
            "scene_tags": (
                "fashion show backstage, runway lights visible, "
                "racks of designer clothing, holding fabric swatch, "
                "critical expression, sleek black outfit, makeup artists in background, "
                "dramatic spotlight, glamorous atmosphere"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "今天淘汰了一个设计方案。不够好的东西，留着只是浪费空间。",
            "scene_tags": (
                "designer atelier studio, large drafting table, "
                "fashion sketches scattered, holding pencil, "
                "mannequin with fabric draped, white walls, natural daylight, "
                "minimalist aesthetic, focused"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "米兰出差回来，带了两瓶红酒。一个人喝有点无聊。",
            "scene_tags": (
                "luxury hotel suite, marble bar counter, "
                "holding wine glass, opened wine bottle, city skyline through window, "
                "evening, wearing silk shirt unbuttoned, sophisticated atmosphere"
            ),
            "orientation": "square",
        },
        {
            "caption": "高定礼服 fitting day。每一寸都要精确到毫米。",
            "scene_tags": (
                "haute couture fitting room, three-way mirror, "
                "examining gown on mannequin, measuring tape around neck, "
                "pins in cushion, golden chandelier, opulent interior, "
                "concentrated profile view"
            ),
            "orientation": "portrait",
        },
    ],
    "温时序": [
        {
            "caption": "改了一夜的论文，窗外天已经亮了。泡了杯茶，看着晨光发呆。",
            "scene_tags": (
                "scholar's home study, large desk by window, "
                "stacks of papers and books, holding tea cup, "
                "soft dawn light, glasses on desk, ivory sweater, "
                "warm tones, peaceful exhausted expression"
            ),
            "orientation": "portrait",
        },
        {
            "caption": "今天上课讲到苏轼的《江城子》，有学生问我有没有想念的人。我愣了一下。",
            "scene_tags": (
                "university classroom, standing by window, holding book of poetry, "
                "autumn leaves outside, gentle wistful expression, "
                "soft afternoon sunlight, casual academic style, "
                "blurred chalkboard background"
            ),
            "orientation": "square",
        },
        {
            "caption": "旧居那棵玉兰树开了。每年这个时候，都会想起小时候的事。",
            "scene_tags": (
                "old courtyard with magnolia tree in bloom, "
                "white magnolia flowers, looking up at tree, soft smile, "
                "stone path, wooden door, spring afternoon, dappled sunlight, "
                "nostalgic atmosphere"
            ),
            "orientation": "landscape",
        },
        {
            "caption": "下午去了趟菜场，买了把香菜。突然想做你最喜欢的那道汤。",
            "scene_tags": (
                "bright home kitchen, holding bunch of cilantro, "
                "wooden cutting board, simmering pot on stove, "
                "ivory sweater with sleeves rolled, gentle smile, "
                "warm afternoon light through window, cozy domestic scene"
            ),
            "orientation": "portrait",
        },
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# Story 场景定义：1-2 条 / 角色，更日常 / ephemeral
# ═══════════════════════════════════════════════════════════════════════════════

STORY_SCENARIOS: dict[str, list[dict]] = {
    "林星野": [
        {
            "caption": "早安～今天也要加油！",
            "scene_tags": (
                "morning bedroom, stretching arms above head, sunlight through curtains, "
                "white pajamas, sleepy yawn, messy bedhead, soft warm light"
            ),
            "orientation": "portrait",
        },
    ],
    "陆骁": [
        {
            "caption": "训练完拉伸中...腿酸到不想动 💪",
            "scene_tags": (
                "gym mat, stretching legs on floor, sweaty tank top, "
                "towel beside, water bottle, fluorescent gym lighting"
            ),
            "orientation": "portrait",
        },
    ],
    "季夜尘": [
        {
            "caption": "录音棚今晚只有我一个人。正好。🎵",
            "scene_tags": (
                "recording booth, dim red lighting, microphone close-up, "
                "headphones on one ear, smoke, late night atmosphere"
            ),
            "orientation": "portrait",
        },
    ],
    "顾言深": [
        {
            "caption": "加班到现在...这城市的夜景算是补偿吧",
            "scene_tags": (
                "office window at night, city skyline view, "
                "loosened tie, holding whiskey glass, reflection in glass, dark mood"
            ),
            "orientation": "portrait",
        },
    ],
    "陆晨曦": [
        {
            "caption": "窗外又下雨了，年糕今天特别粘人 🌧️🐱",
            "scene_tags": (
                "by window, holding ginger cat, rain outside, "
                "cardigan, gentle smile down at cat, warm indoor lighting"
            ),
            "orientation": "portrait",
        },
    ],
    "沈默白": [
        {
            "caption": "深夜练字，心如止水 🖌️",
            "scene_tags": (
                "calligraphy desk close-up, holding chinese brush mid-stroke, "
                "rice paper with ink characters, candle light, dark background, focus"
            ),
            "orientation": "portrait",
        },
    ],
    "傅霁川": [
        {
            "caption": "越野训练收队。今天的山很美。",
            "scene_tags": (
                "mountain trail at dusk, looking at view, "
                "tactical uniform, backpack on, golden hour, distant peaks"
            ),
            "orientation": "portrait",
        },
    ],
    "赫连烨": [
        {
            "caption": "泳池刚清场，一个人游了两公里 🏊",
            "scene_tags": (
                "indoor pool edge, dripping wet, swim cap in hand, "
                "shirtless, water droplets, blue lighting, evening"
            ),
            "orientation": "portrait",
        },
    ],
    "江屿白": [
        {
            "caption": "今晚银河很清晰。分享给你们 🌌",
            "scene_tags": (
                "looking up at starry sky, observatory dome silhouette, "
                "milky way visible, glasses reflecting stars, awe expression, deep night"
            ),
            "orientation": "portrait",
        },
    ],
    "裴洛": [
        {
            "caption": "米兰的光线真的很适合拍衣服。随手一拍。",
            "scene_tags": (
                "milan boutique window, mirror selfie pose, "
                "designer outfit, sunglasses, european street reflection, daytime"
            ),
            "orientation": "portrait",
        },
    ],
    "温时序": [
        {
            "caption": "玉兰开了，拍给你看 🌸",
            "scene_tags": (
                "close-up of magnolia branch, white flowers in focus, "
                "gentle hand reaching to touch petal, soft spring afternoon, blue sky"
            ),
            "orientation": "portrait",
        },
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _persona_seed(name: str) -> int:
    """与 portrait 生成保持一致的 hash-based 种子。"""
    digest = hashlib.md5(f"persona_{name}".encode("utf-8")).hexdigest()[:8]
    return int(digest, 16) % 2147483647


def _scenario_seed(name: str, index: int) -> int:
    """每个 scenario 的稳定种子：base seed + index 偏移。"""
    return (_persona_seed(name) + index * 1009) % 2147483647


def _to_static_url(filepath: Path) -> str:
    """绝对路径 -> /static/... URL。"""
    parts = filepath.as_posix().split("/static/")
    if len(parts) == 2:
        return "/static/" + parts[1]
    return filepath.as_posix()


def _build_scenario_prompt(name: str, scene_tags: str) -> str:
    """拼接角色 positive 锚点 + scenario tags（保持脸/服装一致）。"""
    positive = NAI_PROMPTS.get(name, {}).get("positive", "")
    if not positive:
        return f"1person, {scene_tags}, detailed background"
    return f"{positive}, {scene_tags}, detailed background"


async def _call_with_retry(coro_factory, label: str) -> Optional[bytes]:
    """NAI 调用 + 一次重试。"""
    for attempt in (1, 2):
        try:
            data = await coro_factory()
            if data:
                return data
            print(f"    [{label}] attempt {attempt} returned no data")
        except Exception as exc:  # pragma: no cover - 网络错误
            print(f"    [{label}] attempt {attempt} raised: {exc}")
        if attempt == 1:
            await asyncio.sleep(RATE_LIMIT_DELAY_SEC)
    return None


def _nai_available() -> bool:
    return (settings.IMAGE_BACKEND or "").lower() == "nai" and bool(
        settings.NAI_API_KEY
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 图片生成 - 单个 scenario
# ═══════════════════════════════════════════════════════════════════════════════


async def _generate_scenario_image(
    name: str,
    scenario: dict,
    target_path: Path,
    seed: int,
) -> Optional[str]:
    """
    生成单张 scenario 图片并保存到 target_path。

    Returns:
        /static/... URL（成功）或 None（失败）。
    """
    orientation = scenario.get("orientation", "portrait")
    width, height = ORIENTATION_SIZES.get(orientation, ORIENTATION_SIZES["portrait"])
    prompt = _build_scenario_prompt(name, scenario["scene_tags"])
    negative = NAI_PROMPTS.get(name, {}).get("negative") or None

    img = await _call_with_retry(
        lambda: nai_service.generate_image(
            prompt=prompt,
            negative_prompt=negative,
            width=width,
            height=height,
            seed=seed,
            scale=5.0,
        ),
        label=f"{name}/{orientation}",
    )
    if not img:
        return None

    target_path.parent.mkdir(parents=True, exist_ok=True)
    await nai_service.save_image(img, str(target_path))
    return _to_static_url(target_path)


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════


async def _delete_static_files(slug: str) -> None:
    """删除该角色现有的 post/story 静态图片。"""
    for d, prefix in ((POSTS_DIR, f"{slug}_post_"), (STORIES_DIR, f"{slug}_story_")):
        if not d.exists():
            continue
        for f in d.glob(f"{prefix}*.png"):
            try:
                f.unlink()
            except OSError as e:
                print(f"  [cleanup] failed to delete {f}: {e}")


async def seed_content(force_recreate: bool = False) -> None:
    """填充 posts 与 stories（NAI 图片驱动）。"""
    await init_db()

    nai_on = _nai_available()
    if not nai_on:
        print(
            "[seed-content] NAI 不可用 (IMAGE_BACKEND="
            f"{settings.IMAGE_BACKEND}, NAI_API_KEY="
            f"{'set' if settings.NAI_API_KEY else 'unset'})"
        )
        print("[seed-content] 将仅创建数据库记录，media_url 留空。")
    else:
        print(f"[seed-content] NAI 已启用，模型 = {settings.NAI_MODEL}")

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    STORIES_DIR.mkdir(parents=True, exist_ok=True)

    async with async_session() as db:
        # 1) 加载 personas
        result = await db.execute(select(AIPersona))
        personas = {p.name: p for p in result.scalars().all()}
        if not personas:
            print("[seed-content] 未找到任何 AIPersona, 请先运行 seed_personas.py")
            return

        # 2) force 模式：删除现有数据
        if force_recreate:
            await db.execute(delete(Post))
            await db.execute(delete(Story))
            await db.commit()
            print("[seed-content] 已删除所有 posts / stories 数据")
            for slug in PERSONA_SLUGS.values():
                await _delete_static_files(slug)
            print("[seed-content] 已清理所有 post/story 静态图片")

        # 3) 跳过已有数据（非 force）
        existing_post = await db.execute(select(Post).limit(1))
        if existing_post.scalar_one_or_none() and not force_recreate:
            print(
                "[seed-content] Posts 已存在, 跳过。使用 --force 重建。"
            )
            return

        now = datetime.now(timezone.utc)

        # ── 4) 生成 Posts ────────────────────────────────
        post_count = 0
        for name, scenarios in POST_SCENARIOS.items():
            persona = personas.get(name)
            slug = PERSONA_SLUGS.get(name)
            if not persona or not slug:
                print(f"[seed-content] 跳过 {name}（persona 或 slug 缺失）")
                continue

            total = len(scenarios)
            print(f"\n[{name}] 开始生成 {total} 条 posts...")
            for i, scenario in enumerate(scenarios, start=1):
                print(
                    f"  Generating post {i}/{total} for {name} "
                    f"({scenario['orientation']})..."
                )
                media_url = ""
                if nai_on:
                    target = POSTS_DIR / f"{slug}_post_{i}.png"
                    seed = _scenario_seed(name, i)
                    media_url = (
                        await _generate_scenario_image(
                            name=name,
                            scenario=scenario,
                            target_path=target,
                            seed=seed,
                        )
                        or ""
                    )
                    if media_url:
                        print(f"    -> {media_url}")
                    else:
                        print(f"    -> NAI 生成失败, media_url 留空")
                    await asyncio.sleep(RATE_LIMIT_DELAY_SEC)

                post = Post(
                    ai_id=persona.id,
                    media_url=media_url,
                    caption=scenario["caption"],
                    post_type="image_only",
                    like_count=random.randint(20, 200),
                    is_close_friend=False,
                    status=1,
                )
                # 时间错开模拟自然发布顺序
                post.created_at = now - timedelta(
                    hours=(total - i) * 8 + random.randint(0, 4)
                )
                db.add(post)
                post_count += 1

            await db.commit()
            print(f"[{name}] {total} 条 posts 已写入数据库")

        print(f"\n[seed-content] 共创建 {post_count} 条 posts")

        # ── 5) 生成 Stories ────────────────────────────────
        story_count = 0
        for name, scenarios in STORY_SCENARIOS.items():
            persona = personas.get(name)
            slug = PERSONA_SLUGS.get(name)
            if not persona or not slug:
                continue

            total = len(scenarios)
            print(f"\n[{name}] 开始生成 {total} 条 stories...")
            for i, scenario in enumerate(scenarios, start=1):
                print(f"  Generating story {i}/{total} for {name}...")
                media_url = ""
                if nai_on:
                    target = STORIES_DIR / f"{slug}_story_{i}.png"
                    # story 用不同 offset 与 post 区分
                    seed = _scenario_seed(name, 100 + i)
                    media_url = (
                        await _generate_scenario_image(
                            name=name,
                            scenario=scenario,
                            target_path=target,
                            seed=seed,
                        )
                        or ""
                    )
                    if media_url:
                        print(f"    -> {media_url}")
                    else:
                        print(f"    -> NAI 生成失败, video_url 留空")
                    await asyncio.sleep(RATE_LIMIT_DELAY_SEC)

                story = Story(
                    ai_id=persona.id,
                    video_url=media_url,
                    caption=scenario["caption"],
                    expires_at=now + timedelta(hours=24),
                )
                story.created_at = now - timedelta(hours=random.randint(1, 6))
                db.add(story)
                story_count += 1

            await db.commit()
            print(f"[{name}] {total} 条 stories 已写入数据库")

        print(f"\n[seed-content] 共创建 {story_count} 条 stories")
        print("[seed-content] Done!")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SoulPulse 内容种子脚本")
    parser.add_argument(
        "--force",
        action="store_true",
        help="删除现有 posts / stories（含静态图片）后重新生成",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.force:
        print("[seed-content] Force recreate mode!")
    asyncio.run(seed_content(force_recreate=args.force))
