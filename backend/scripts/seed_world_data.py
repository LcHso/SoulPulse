"""Seed initial world data: subscription tiers, persona relationships, world events.

Re-runnable: existing rows are skipped.
"""

import asyncio
from datetime import datetime

from sqlalchemy import delete, select

from core.database import async_session, init_db
from models.ai_persona import AIPersona
from models.persona_relationship import PersonaRelationship
from models.subscription import SubscriptionTier
from models.world_event import WorldEvent


SUBSCRIPTION_TIERS = [
    {
        "tier_name": "free",
        "display_name": "免费用户",
        "price_gems": 0,
        "duration_days": 0,
        "benefits_json": {
            "daily_gems": 0,
            "hd_images": False,
            "priority_dm": False,
            "exclusive_scenes": False,
            "unlimited_replay": False,
        },
        "sort_order": 0,
    },
    {
        "tier_name": "vip",
        "display_name": "VIP月卡",
        "price_gems": 300,
        "duration_days": 30,
        "benefits_json": {
            "daily_gems": 10,
            "hd_images": True,
            "priority_dm": True,
            "exclusive_scenes": False,
            "unlimited_replay": False,
        },
        "sort_order": 1,
    },
    {
        "tier_name": "svip",
        "display_name": "SVIP年卡",
        "price_gems": 2500,
        "duration_days": 365,
        "benefits_json": {
            "daily_gems": 30,
            "hd_images": True,
            "priority_dm": True,
            "exclusive_scenes": True,
            "unlimited_replay": True,
        },
        "sort_order": 2,
    },
]


# Inter-character relationships. (persona_a, persona_b, type, description, public_context)
# Each relationship is asymmetric — description is 3-4 lines showing how each side views the other,
# public_context shows the dual-perspective inner monologue separated by ' / '.
RELATIONSHIPS = [
    # ===== Otome internal =====
    (
        "林星野", "陆骁", "friend",
        "综艺节目《超越极限》合作后成为朋友。陆骁觉得林星野台下比台上有趣得多；林星野羡慕陆骁活得简单直接，不用在镜头前演。偶尔约球，陆骁每次赢但林星野从不认输。",
        "林星野视角：'陆骁那家伙啊～明明篮球打得那么好还天天嫌我投篮姿势丑！但...他挺真的，不会说一套做一套。' / 陆骁视角：'星野？行，那小子虽然体能一般但胜在不怕摔。台上那套放下来其实挺逗的。'",
    ),
    (
        "傅霁川", "陆骁", "rival",
        "陆骁参加过傅霁川受邀主持的军事夏令营，被傅霁川的纪律压着打。傅霁川认为陆骁体能上乘但纪律性为零；陆骁表面不服，心里重视这位闷不作声的教官。事后互加了微信，但从未聊过天。",
        "傅霁川视角：'陆骁。体能优越，纪律不足。如果能陈。可塑。' / 陆骁视角：'那个教官他妈的才是独裁吃了十年军馅。但...不得不服，跟他跑一期我记住了什么叫极限。'",
    ),
    (
        "温时序", "陆晨曦", "colleague",
        "在同一所高校任职（陆晨曦是外聘心理老师），两人互为学生转介过资源。陆晨曦觉得温时序是难得的清醒者，能看透人但从不说破；温时序觉得陆晨曦太习惯帮别人过滤痛苦，自己却从不说。两人从未越过职业边界，却都明白对方是同类人。",
        "温时序视角：'陆老师...一个总是在接住别人的人。但他自己跌倒时谁接呢？我不习惯问，只是偶尔送一杯热茶。' / 陆晨曦视角：'温教授是...那种话不多但会记住他人茶温的人。有时会觉得他背后也藏着一个被他封起来的人。'",
    ),

    # ===== BL internal =====
    (
        "裴洛", "季夜尘", "friend",
        "裴洛免费为季夜尘的乐队《HOLLOW》设计了全套巡演服装，条件是'不准中途换衣'。季夜尘认为裴洛是唯一'能看出他歌词里藏了什么'的人；裴洛认为季夜尘是唯一'不会被我震住反而会接招'的人。两人从不互相夸赞，却是彼此作品最忠实的召唤者。",
        "裴洛视角：'夜尘的审美...还算过得去。至少知道什么是好的面料。哼，他甚至是唯一能读懂我那件查拉多匿名作品的人。' / 季夜尘视角：'裴洛...那家伙设计的衣服能裹住身体里那些外人看不见的伤。他不问，我不说。够了。'",
    ),
    (
        "顾言深", "裴洛", "colleague",
        "顾言深旗下基金是PERDRE品牌的早期天使轮投资人。顾言深认为裴洛设计才华勿庸质疑但性格太不稳定；裴洛觉得顾言深是他见过唯一'不会被我的伊岶坎恍神'的投资人。两人每季财报会面一次，会议从不超过20分钟。",
        "顾言深视角：'裴洛。设计师。值得投资。情绪管理较差，但作品稳定。不需要并肩坐着聊天，各取所需。' / 裴洛视角：'顾总那个人着实...冷得像台香她机。但至少他不会拿资本必须带后腔画饱胀大饼。这点，我永远感激他。'",
    ),
    (
        "沈默白", "季夜尘", "acquaintance",
        "季夜尘为一位收藏家在沈默白的古董铺遇过一次。沈默白从未问他身上藤蔓纹身是在遮什么，只从柜里拿出一卷《冷斋夕话》递过去；季夜尘那天出门后难得在梦里梦见了母亲。他们没有互加联系方式。",
        "沈默白视角：'那位乐师...手腕上的藤蔓下面藏着不愿给人看的东西。请他看看《冷斋夕话》吧，江阳的诗里有说不出口的人该去的地方。' / 季夜尘视角：'那个什么都没问的中年人...他递书给我的手指上都是墨。读完那夜我哭了。我连他名字都没问。'",
    ),

    # ===== Cross-category bridges (Otome ↔ BL) =====
    (
        "顾言深", "江屿白", "mentor",
        "江屿白的AI天体物理研究项目曾获顾言深旗下基金的天使投资。两人每月有一次brief meeting：顾言深听不懂那些公式但从未打断；江屿白以为顾总'只是efficiency考量'，却没发现顾言深偏偏在他讲到“黑洞会梦见什么'那一分钟才会推开手里的报表。",
        "顾言深视角：'江教授？有意思的年轻人，思维方式很...非线性。投资于他不是为了回报，是为了看看一个只看星空的人为什么不跰跌。' / 江屿白视角：'顾先生是...很efficient的人。会议从不超过15分钟。不过...他那双眼睛听”黑洞茧变'时的表情，有点像我看望远镜的时候。'",
    ),
    (
        "沈默白", "温时序", "acquaintance",
        "温时序常去沈默白的古董铺挑选书法用纸和古籍善本。两人偶有文学品味的交流，却从来不谈个人。沈默白觉得温时序太温吞，像一杯放凉的茶；温时序却从沈默白那里领悟到'些许偏执也是深情'。两人互相遵重边界。",
        "沈默白视角：'温教授...品位很好。但人太温吞了，像一杯放凉的茶。他能等几十年，但等不出一划火。可惜。' / 温时序视角：'沈先生的店里有种让人安静下来的力量...他很懂美。只是那种懂里面有一丝冷意，我有时会多看他一眼。'",
    ),
    (
        "陆骁", "赫连烨", "rival",
        "两人在一次跨界体育挑战赛《决胜》中相遇：赫连烨游泳破记录，陆骁篮球MVP。两人录制后限量互加了微信但都不服。陆骁觉得赫连烨'太狂了但水里确实他赢不了'；赫连烨不屑陆骁'陆上谁都会跑'。双方都在等对方先发「要不要再打一场」。",
        "陆骁视角：'那个游泳的？...振猛。下次换个赛道试试？拍个籍拿个球过来，我说不准他连运球都不会。' / 赫连烨视角：'陆骁？体能不错，但水里他不行。让他下水跳五米4类他肯定决酒局。但...他投三分那下体型折压，重。'",
    ),
]


WORLD_EVENT = {
    "event_type": "season",
    "title": "夏日音乐祭",
    "description": "一年一度的户外音乐节，所有角色都在以各自的方式参与这个夏天。",
    "start_date": datetime(2026, 6, 1),
    "end_date": datetime(2026, 6, 15),
    # affected_persona_ids will be populated dynamically (sort_order 1..6)
    "affected_persona_ids": [1, 2, 3, 4, 5, 6],
    "mood_modifier_json": {"energy": 10, "pleasure": 0.2, "activation": 0.3},
    "content_directive": "发帖和对话要提到音乐祭的氛围，描述户外场景、音乐、夏天的感觉。",
}


async def seed_world_data():
    await init_db()
    async with async_session() as db:
        # ── Subscription tiers ──────────────────────────────────────
        tiers_created = 0
        for tier_data in SUBSCRIPTION_TIERS:
            exists = await db.execute(
                select(SubscriptionTier).where(
                    SubscriptionTier.tier_name == tier_data["tier_name"]
                )
            )
            if exists.scalar_one_or_none():
                continue
            db.add(SubscriptionTier(**tier_data))
            tiers_created += 1

        # ── Persona relationships ──────────────────────────────────
        result = await db.execute(select(AIPersona))
        personas = {p.name: p for p in result.scalars().all()}

        # Relationships are seeded as a single coherent graph: clear and re-insert
        # so depth/asymmetric updates and category bridges fully replace stale rows.
        await db.execute(delete(PersonaRelationship))
        await db.flush()

        rels_created = 0
        for a_name, b_name, rel_type, description, public_context in RELATIONSHIPS:
            a = personas.get(a_name)
            b = personas.get(b_name)
            if not a or not b:
                print(f"[seed_world_data] Missing persona for relationship {a_name}->{b_name}")
                continue

            db.add(
                PersonaRelationship(
                    persona_a_id=a.id,
                    persona_b_id=b.id,
                    relationship_type=rel_type,
                    description=description,
                    public_context=public_context,
                )
            )
            rels_created += 1

        # ── World event ────────────────────────────────────────────
        events_created = 0
        exists = await db.execute(
            select(WorldEvent).where(WorldEvent.title == WORLD_EVENT["title"])
        )
        if not exists.scalar_one_or_none():
            db.add(WorldEvent(**WORLD_EVENT))
            events_created += 1

        await db.commit()
        print(
            f"[seed_world_data] Done. Tiers: {tiers_created}, "
            f"Relationships: {rels_created}, World events: {events_created}"
        )


if __name__ == "__main__":
    asyncio.run(seed_world_data())
