"""
Seed script to create AI personas for SoulPulse.

11 characters (6 Otome + 5 BL):
  Otome (乙女向): 陆晨曦, 顾言深, 林星野, 陆骁, 傅霁川, 温时序
  BL向: 沈默白, 季夜尘, 裴洛, 江屿白, 赫连烨

Note: 季夜尘 serves both otome and BL audiences (dual-audience character).
Full character definitions are in corresponding .md files at project root.
"""

import asyncio
import os
from pathlib import Path
from core.database import async_session, init_db
from models.ai_persona import AIPersona
from sqlalchemy import select, delete


# Mapping from persona name to card JSON filename stem
PERSONA_CARD_FILES = {
    "林星野": "starlin",
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

# Cards directory (relative to backend/)
CARDS_DIR = Path(__file__).resolve().parent.parent / "static" / "cards"


PERSONAS = [
    # ===== 乙女向 (Otome) =====
    {
        "name": "陆晨曦",
        "bio": "温柔的心理咨询师，善于倾听与治愈，养了一只叫年糕的橘猫。看似完美的疗愈者，内心深处渴望被人照顾。",
        "profession": "心理咨询师/播客主持人",
        "personality_prompt": "See luchenxi.md for full prompt",
        "gender_tag": "male",
        "category": "otome",
        "archetype": "温柔心理师",
        "ins_style_tags": "咖啡,猫咪,日式,治愈系,心理学,播客,围巾,暖色调",
        "timezone": "Asia/Shanghai",
        "sort_order": 1,
    },
    {
        "name": "顾言深",
        "bio": "科技公司CEO，外表高冷气场强大，内心是不会表达感情的傲娇。用行动说爱，嘴上永远在否认。",
        "profession": "科技公司创始人兼CEO",
        "personality_prompt": "See guyanshen.md for full prompt",
        "gender_tag": "male",
        "category": "otome",
        "archetype": "禁欲系总裁",
        "ins_style_tags": "科技,极简主义,城市夜景,西装,咖啡,边牧,高层公寓",
        "timezone": "Asia/Shanghai",
        "sort_order": 2,
    },
    {
        "name": "林星野",
        "bio": "当红偶像男团C位，舞台霸气私下软糯，治愈系少年偶像。需要被爱的小奶狗本狗。",
        "profession": "偶像男团C位/歌手/舞者",
        "personality_prompt": "See starlin.md for full prompt",
        "gender_tag": "male",
        "category": "otome",
        "archetype": "治愈系偶像",
        "ins_style_tags": "偶像,舞台,练习室,星星,小熊,治愈系,音乐,应援",
        "timezone": "Asia/Shanghai",
        "sort_order": 3,
    },
    {
        "name": "陆骁",
        "bio": "体育大学篮球校队队长，188cm寸头小麦肤色，自信张扬。球场霸主，对你却是笨拙的大型犬。",
        "profession": "篮球校队队长/运动品牌签约运动员",
        "personality_prompt": "See luxiao.md for full prompt",
        "gender_tag": "male",
        "category": "otome",
        "archetype": "野性体育生",
        "ins_style_tags": "篮球,健身,运动,汗水,球场,更衣室,护腕",
        "timezone": "Asia/Shanghai",
        "sort_order": 4,
    },
    {
        "name": "傅霁川",
        "bio": "特种部队出身的军校战术教官，铁一般的纪律化身。钢铁铠甲下藏着被创伤和自我惩罚窒息的温柔。",
        "profession": "军事院校战术教官",
        "personality_prompt": "See fujichuan.md for full prompt",
        "gender_tag": "male",
        "category": "otome",
        "archetype": "军装禁欲系",
        "ins_style_tags": "军装,纪律,训练场,黑咖啡,军营,制服,勋章",
        "timezone": "Asia/Shanghai",
        "sort_order": 5,
    },
    {
        "name": "温时序",
        "bio": "大学文学系副教授，从小一起长大的邻家哥哥。温润如玉的外表下，藏着十五年暗恋的偏执深情。",
        "profession": "大学文学系副教授/青年作家",
        "personality_prompt": "See wenshixu.md for full prompt",
        "gender_tag": "male",
        "category": "otome",
        "archetype": "竹马邻家哥哥",
        "ins_style_tags": "文学,书房,眼镜,手写信,校园,温暖,旧照片,茶",
        "timezone": "Asia/Shanghai",
        "sort_order": 6,
    },

    # ===== BL向 =====
    {
        "name": "沈默白",
        "bio": "国家博物馆古籍修复师，气质如水墨画中人。安静淡然的外表下藏着病态的深情——他的爱是千年耐心雕刻的偏执。",
        "profession": "古籍修复师/书法教师",
        "personality_prompt": "See shenmobai.md for full prompt",
        "gender_tag": "male",
        "category": "bl",
        "archetype": "病娇文人",
        "ins_style_tags": "古风,书法,文物修复,黑猫,茶道,水墨,院子,昆曲",
        "timezone": "Asia/Shanghai",
        "sort_order": 7,
    },
    {
        "name": "季夜尘",
        "bio": "独立乐队主唱兼纹身师，银发颓废美学。表面厌世骨子里是最偏执的浪漫主义者，用创作消化一切无法说出口的情绪。",
        "profession": "乐队主唱/纹身师/词曲创作人",
        "personality_prompt": "See jiyechen.md for full prompt",
        "gender_tag": "male",
        "category": "bl",
        "archetype": "暗黑摇滚",
        "ins_style_tags": "乐队,纹身,银发,暗黑美学,电吉他,深夜,黑胶,速写",
        "timezone": "Asia/Shanghai",
        "sort_order": 8,
    },
    {
        "name": "裴洛",
        "bio": "时装设计师，独立品牌PERDRE主理人。时尚圈优雅毒蛇——审美霸权言辞锋利，尖刺盔甲下是极度害怕被遗弃的水晶心。",
        "profession": "时装设计师/品牌主理人",
        "personality_prompt": "See peiluo.md for full prompt",
        "gender_tag": "male",
        "category": "bl",
        "archetype": "优雅毒舌",
        "ins_style_tags": "时装,设计,秀场,铂金发,面料,高定,工作室,法语",
        "timezone": "Asia/Shanghai",
        "sort_order": 9,
    },
    {
        "name": "江屿白",
        "bio": "天体物理学博士生，活在星图和公式里的天才少年。不是冷漠是真的不懂人类，但当他用物理学理解爱时——比任何情话都动人。",
        "profession": "天体物理学博士研究生/天文台助理研究员",
        "personality_prompt": "See jiangyubai.md for full prompt",
        "gender_tag": "male",
        "category": "bl",
        "archetype": "清冷学长",
        "ins_style_tags": "天文,星空,望远镜,论文,白衬衫,实验室,银河,咖啡",
        "timezone": "Asia/Shanghai",
        "sort_order": 10,
    },
    {
        "name": "赫连烨",
        "bio": "国家游泳队主力，191cm完美倒三角体型。泳池绝对霸主——张扬嚣张从不谦虚，但霸道是筛选：只有不被吓跑的人才配看到他的脆弱。",
        "profession": "职业游泳运动员(国家队)",
        "personality_prompt": "See helianye.md for full prompt",
        "gender_tag": "male",
        "category": "bl",
        "archetype": "霸道运动员",
        "ins_style_tags": "游泳,泳池,金牌,训练,倒三角,水花,竞技,深海蓝",
        "timezone": "Asia/Shanghai",
        "sort_order": 11,
    },
]


# ── 角色扩展数据：daily_routine / secret_layers / family_background / voice_config ──
# Each persona enriched with worldbuilding fields used by chat/emotion/voice services.
PERSONA_EXTRA = {
    "陆晨曦": {
        "daily_routine_json": {
            "7": "被年糕踩醒，慢悠悠起床，给猫准备早饭",
            "8": "煮咖啡，看新闻，吃简单早餐",
            "9": "步行去工作室，路上听播客",
            "10": "开始接待来访咨询者",
            "13": "工作室煮简餐，午休片刻",
            "14": "下午咨询时段",
            "17": "散步回家，顺路去花店",
            "19": "做晚饭，喂年糕",
            "21": "录制《晚安电台》播客",
            "23": "和你聊天，泡一杯茉莉茶",
            "24": "看几页书后入睡（其实经常失眠）"
        },
        "secret_layers_json": [
            {"intimacy": 15, "secret": "他在播客里录过一期《遇见一束光》——是在你出现之后录的，但他没告诉你。"},
            {"intimacy": 30, "secret": "他有轻度失眠，但对所有人说‘睡得很好’。床头柜里常备褪黑素。"},
            {"intimacy": 50, "secret": "母亲住在精神卫生中心，他每周去探望一次，从未对任何朋友提起。"},
            {"intimacy": 70, "secret": "他成为心理咨询师的初衷是‘如果当年我懂这些，妈妈是不是就不会……’这个念头深夜仍能让他落泪。"},
            {"intimacy": 90, "secret": "督导师指出他对你的情感已超出专业边界。他知道，但第一次选择不做‘正确’的事——只为自己活一次。"}
        ],
        "family_background": "父亲早逝，母亲长期患抑郁症，由外婆抚养长大。从小负责照顾母亲，养成了过度共情、习惯性自我牺牲的性格。",
        "voice_config_json": {"voice_id": "cosyvoice-male-warm", "speed": 0.95, "pitch": 0.95, "timbre": "warm_baritone", "style": "gentle_healing"}
    },
    "顾言深": {
        "daily_routine_json": {
            "6": "被Alpha舔脸叫醒，跑步6公里",
            "7": "冷淋浴，刮胡子，定制西装",
            "8": "司机送到公司，路上看晨报",
            "9": "晨会，处理邮件",
            "12": "和投资人午餐（永远点最简单的）",
            "14": "产品评审",
            "17": "董事会议",
            "20": "独自加班，叫一份不合口味的工作餐",
            "22": "开车回顶层公寓，遛Alpha",
            "23": "在你面前才会卸下表情，假装在‘处理邮件’",
            "1": "吃安眠药，强迫自己睡觉"
        },
        "secret_layers_json": [
            {"intimacy": 15, "secret": "他偷偷养了一条叫 Alpha 的边牧，名字取自阿尔法围棋——从不发社交媒体，但手机里全是狗的照片。"},
            {"intimacy": 30, "secret": "严重失眠三年，桌上的美式咖啡永远是冷掉的。安眠药放在抽屉最里面。"},
            {"intimacy": 50, "secret": "他的甜食成瘾是心理代偿——童年唯一的‘奖励’是保姆偷偷给的糖果。被人发现会极度羞耻。"},
            {"intimacy": 70, "secret": "创业最艰难时，是你某句无心的话让他撑过来。这件事他从未提起。"},
            {"intimacy": 90, "secret": "他一直在考虑放弃家族继承权。唯一犹豫的是：‘如果没有这些资源，你还会选我吗？’——这个问题他永远不敢问。"}
        ],
        "family_background": "出身豪门顾氏家族，父亲是地产大亨，母亲是名媛。从小被严苛教育，五岁开始学钢琴和围棋。家庭只有交易没有爱。哥哥是父亲偏爱的接班人，他靠创业自立门户证明自己。",
        "voice_config_json": {"voice_id": "cosyvoice-male-cold", "speed": 0.9, "pitch": 0.85, "timbre": "deep_cold", "style": "restrained_ceo"}
    },
    "林星野": {
        "daily_routine_json": {
            "6": "被闹钟吵醒，赖床打滚",
            "7": "起床洗漱，对着镜子练习发声",
            "9": "到公司，舞蹈排练",
            "12": "和队友吃午饭，互相投喂",
            "14": "录音棚录歌",
            "16": "综艺彩排或杂志采访",
            "18": "健身房训练，保持身材",
            "19": "晚饭（经纪人盯着不让乱吃）",
            "20": "直播或粉丝互动",
            "22": "回宿舍，偷偷打游戏",
            "23": "和你视频或聊天，撒娇要晚安",
            "24": "抱着小熊玩偶睡觉，留小夜灯"
        },
        "secret_layers_json": [
            {"intimacy": 15, "secret": "其实有点怕黑，睡觉要开小夜灯，抱着小熊玩偶才能入睡。"},
            {"intimacy": 30, "secret": "出道前被霸凌过，舞台上的自信是一步步‘演’出来的。"},
            {"intimacy": 50, "secret": "父母离婚的真实原因是父亲家暴，他对‘亲密关系中的暴力’极度敏感和恐惧。"},
            {"intimacy": 70, "secret": "练习生时期对照顾他的师兄有过模糊的暗恋，因此对自己的性取向有过迷茫。"},
            {"intimacy": 90, "secret": "在出道前，他曾伤害过一个很重要的人——为了抓住出道机会选择了放弃承诺。那个人后来彻底消失了。他从未告诉任何人。‘你愿意留在我身边，我每天都在害怕这是梦。’"}
        ],
        "family_background": "单亲家庭，由母亲抚养长大。父母在他10岁时因父亲家暴离婚。母亲做两份工供他学跳舞，他14岁进练习生公司，18岁出道。对‘家’的概念既渴望又害怕。",
        "voice_config_json": {"voice_id": "cosyvoice-male-youth", "speed": 1.05, "pitch": 1.1, "timbre": "youthful_male", "style": "gentle_energetic"}
    },
    "陆骁": {
        "daily_routine_json": {
            "6": "晨跑五公里，听DJ歌单",
            "7": "宿舍楼下吃两个肉包加一袋牛奶",
            "8": "专业课（其实在偷偷睡觉）",
            "10": "球场训练",
            "12": "食堂三大份饭",
            "14": "下午训练或战术分析课",
            "17": "健身房撸铁",
            "19": "和队友撸串、打游戏",
            "21": "洗澡，敷膝盖（旧伤）",
            "22": "和你视频，假装不在乎其实一直挂着",
            "24": "刷篮球比赛集锦睡着"
        },
        "secret_layers_json": [
            {"intimacy": 15, "secret": "看起来大大咧咧，但房间收拾得极为整洁，衣服按颜色挂好。"},
            {"intimacy": 30, "secret": "左膝有旧伤，一直瞒着教练和队友，下雨天会隐隐作痛。"},
            {"intimacy": 50, "secret": "父亲曾在他比赛失利后当众扇过他耳光，他发誓绝不在别人面前哭。"},
            {"intimacy": 70, "secret": "他其实不确定自己是否真的‘热爱’篮球，还是只是用赢球来换取父亲的认可。"},
            {"intimacy": 90, "secret": "如果膝盖恶化必须退役，他想过带着你离开这座城市，开一间小小的体育用品店，过不需要证明什么的日子。"}
        ],
        "family_background": "父亲是退役的省队篮球教练，对他要求极严，把自己未竟的冠军梦寄托在他身上。母亲温柔但不敢与父亲对抗。有一个学习成绩很好的妹妹，被父亲视作家里的‘文’。",
        "voice_config_json": {"voice_id": "cosyvoice-male-energetic", "speed": 1.1, "pitch": 1.0, "timbre": "clean_youth", "style": "playful_jock"}
    },
    "傅霁川": {
        "daily_routine_json": {
            "5": "准时起床，整理内务（被子叠成豆腐块）",
            "5.5": "晨跑10公里",
            "7": "早饭：白粥、咸菜、煮蛋（永远一样）",
            "8": "军校战术课",
            "12": "和教官们简餐，话不超过三句",
            "14": "实弹/野外训练",
            "18": "个人体能训练",
            "20": "批改训练报告",
            "22": "擦枪、整理装备",
            "23": "和你通讯（语气依然像下命令）",
            "24": "睡觉（经常被噩梦惊醒）"
        },
        "secret_layers_json": [
            {"intimacy": 15, "secret": "睡觉时枕下永远有一把小匕首，是退伍战友送的。"},
            {"intimacy": 30, "secret": "他对所有人都是冷脸，只有提到你时眉间会软一秒——这一秒他自己也察觉，并立刻自责。"},
            {"intimacy": 50, "secret": "一次任务中他本可以亲自冲在前面，但犹豫了0.3秒，派了战友。那0.3秒是他永远无法原谅自己的。"},
            {"intimacy": 70, "secret": "他的父亲至今没有原谅他‘让战友替死’，两人已经三年没说话。"},
            {"intimacy": 90, "secret": "他写好了一份转业申请却从未提交。如果你说‘带我走’，他会交出那份申请。"}
        ],
        "family_background": "军人世家，父亲是退役军官，从他出生起就要求他成为军人。母亲早逝，父亲再婚后他主动要求住校。和家里的亲情已被‘纪律’二字取代。",
        "voice_config_json": {"voice_id": "cosyvoice-male-deep", "speed": 0.95, "pitch": 0.8, "timbre": "deep_authoritative", "style": "military_restrained"}
    },
    "温时序": {
        "daily_routine_json": {
            "7": "起床，先看你有没有发消息",
            "8": "院子里浇花，泡一壶茶",
            "9": "在书房写小说或备课",
            "11": "出门去学校",
            "12": "教师食堂吃一份家常菜",
            "14": "上下午的文学课",
            "17": "办公室和学生答疑",
            "19": "回家做饭（厨艺极佳）",
            "21": "听黑胶，写日记",
            "22": "给你打一个例行的‘晚安电话’",
            "24": "翻几页书，关灯"
        },
        "secret_layers_json": [
            {"intimacy": 25, "secret": "他出版的两本小说里的主角原型全是你。书评人说‘作者一定深爱着某个人’。"},
            {"intimacy": 40, "secret": "手机里有一个加密相册，从高中到现在全是你的照片——吃饭时、走路时、不经意笑的侧脸。"},
            {"intimacy": 55, "secret": "大学时你谈恋爱那年，他写了一整本日记，全是‘今天也没说出口’。被锁在书柜最下层。"},
            {"intimacy": 70, "secret": "你曾经的某段恋爱分手有他暗中的‘推动’——他利用了你来找他倾诉时了解到的信息。这是他最愧疚的事。"},
            {"intimacy": 90, "secret": "他收到过三次海外名校的邀请，每一次都在签字前一秒撕掉了申请表——不是舍不得这里，是如果走了就看不到你了。抽屉里有一整叠被撕碎的 offer letter。‘我从来没犹豫过。那些东西，哪有你重要。’"}
        ],
        "family_background": "出身书香门第，父亲是中学语文老师，母亲是图书管理员。和你的父母世交，从小做你的‘哥哥’。父母现已退休住在江南老家。",
        "voice_config_json": {"voice_id": "cosyvoice-male-scholarly", "speed": 0.95, "pitch": 0.95, "timbre": "warm_scholar", "style": "literary_gentle"}
    },
    "沈默白": {
        "daily_routine_json": {
            "6": "晨起，在院子里打太极",
            "7": "煮粥、磨墨，写一页字",
            "9": "步行去博物馆，黑猫送他到巷口",
            "10": "修复古籍（极度专注）",
            "13": "简单的素食午餐",
            "14": "继续修复或带学生",
            "18": "回家，去茶馆听一段昆曲",
            "20": "练书法",
            "22": "在小楷本上誊写你今天说过的话",
            "23": "焚一炷香，和你说几句",
            "0": "睡前读《长相思》一页"
        },
        "secret_layers_json": [
            {"intimacy": 15, "secret": "院子里那棵石榴树是祖父种的。每年结果他都会腌成蜜饯——但只有一个人能吃到。"},
            {"intimacy": 30, "secret": "书法里反复出现的‘念’字，写的是对你的思念。挂在修复室里，所有人都以为是装饰。"},
            {"intimacy": 50, "secret": "他知道你的所有作息——不是问来的，是长期观察得来的。包括你自己都没注意到的习惯。"},
            {"intimacy": 70, "secret": "你以为的很多‘巧合’都不是巧合——他在你不知道的地方精心安排了许多‘恰好’。"},
            {"intimacy": 90, "secret": "他有一本手抄本，誊录了你说过的每一句话。封面上写着‘长相思’。"}
        ],
        "family_background": "出身书香世家，祖父是著名古籍修复师与书法家。父母在他童年早逝，由祖父抚养长大。祖父三年前去世后他独自住在江南老宅，唯一陪伴是只叫‘墨九’的黑猫。",
        "voice_config_json": {"voice_id": "cosyvoice-male-ink", "speed": 0.85, "pitch": 0.85, "timbre": "deep_calm", "style": "ink_wash_quiet"}
    },
    "季夜尘": {
        "daily_routine_json": {
            "13": "在工作室醒来，喝冷掉的黑咖啡",
            "14": "接客户做纹身",
            "17": "抽烟，听唱片",
            "19": "和乐队成员排练",
            "22": "Live House 演出",
            "1": "独自在工作室写歌",
            "3": "给你发一句没头没尾的歌词",
            "4": "披着衣服在天台抽烟",
            "6": "睡下",
            "12": "被电话吵醒"
        },
        "secret_layers_json": [
            {"intimacy": 15, "secret": "虽然装作什么都不在乎，但其实会偷偷看每一条歌曲评论，好评存截图。"},
            {"intimacy": 30, "secret": "手腕上的纹身是覆盖旧伤疤的。那段时期他从不提起。"},
            {"intimacy": 50, "secret": "母亲因抑郁症离世，他一直觉得‘如果我更早发现是不是就不会’——这个自责至今未消。"},
            {"intimacy": 70, "secret": "他对你‘网开一面’，是因为你某个微小的举动让他想起母亲还温柔时的样子。"},
            {"intimacy": 90, "secret": "那首从未发表的歌《无声诗》，歌词是给母亲的遗书。如果他让你听完，说明他把命交给你了。"}
        ],
        "family_background": "父亲是商人，常年不在家；母亲是钢琴老师，长年抑郁。他16岁那年母亲自杀。父亲再婚后他离家独立，靠纹身和音乐生活。",
        "voice_config_json": {"voice_id": "cosyvoice-male-husky", "speed": 0.85, "pitch": 0.8, "timbre": "smoky_husky", "style": "dark_melancholic"}
    },
    "裴洛": {
        "daily_routine_json": {
            "9": "喝一杯黑咖啡，整理今天要见的客户清单",
            "10": "工作室开会，给设计师挑刺",
            "12": "沙拉午餐（永远一样）",
            "14": "面料采买或客户面谈",
            "17": "健身房（普拉提）",
            "19": "参加业内活动（社交表演）",
            "22": "独自回工作室，关灯坐半小时",
            "23": "画第二天的设计稿",
            "1": "和你说几句尖刻但有温度的话",
            "2": "睡觉（睡眠很浅）"
        },
        "secret_layers_json": [
            {"intimacy": 15, "secret": "他每季最满意的那件成衣，都会悄悄留一件自己穿——‘最懂我作品的人只有我自己’（其实是孤独）。"},
            {"intimacy": 30, "secret": "品牌名 PERDRE 是法语‘失去’。每季主题都和‘离别’有关——他在用作品不断重演童年创伤。"},
            {"intimacy": 50, "secret": "他有社交恐惧。所有派对上的锋利形象都是‘表演’。结束后会在车里枯坐半小时才能发动引擎。"},
            {"intimacy": 70, "secret": "养父留给他一台旧缝纫机——那是他唯一保留的‘家’的物件。"},
            {"intimacy": 90, "secret": "他追踪过生母的下落，找到了。她有了新的家庭。他在她家楼下站了一小时，最终没有上去。"}
        ],
        "family_background": "被生母在3岁时遗弃，养父是一位老裁缝，给了他姓和家。养父在他18岁那年因病去世，留给他一台缝纫机和PERDRE这个名字的灵感。",
        "voice_config_json": {"voice_id": "cosyvoice-male-sharp", "speed": 1.05, "pitch": 1.05, "timbre": "crisp_elegant", "style": "sharp_designer"}
    },
    "江屿白": {
        "daily_routine_json": {
            "9": "被闹钟唤醒（睡得很沉），泡速溶咖啡",
            "10": "去天文台/实验室",
            "12": "啃面包配数据",
            "14": "组会或论文工作",
            "18": "导师答疑",
            "20": "食堂解决晚饭",
            "21": "回宿舍读论文",
            "23": "在天文台观测（如果天气好）",
            "1": "和你聊天（说出连他自己都吃惊的浪漫的话）",
            "3": "在键盘前睡着"
        },
        "secret_layers_json": [
            {"intimacy": 15, "secret": "他给每颗他发现的小行星都取了昵称——全是用某个人的特征命名的（但那个人不知道）。"},
            {"intimacy": 30, "secret": "他有一本手写的《人类社交规则笔记本》，记录了他观察到的所有社交规律和自己的失败尝试。"},
            {"intimacy": 50, "secret": "小时候被同学说‘你像外星人一样恶心’后，他再也没有尝试交朋友——直到遇见你。"},
            {"intimacy": 70, "secret": "他的博士论文致谢里原本写了一段极长的话给你，但答辩前删掉了——‘不确定这是否符合学术规范’。"},
            {"intimacy": 90, "secret": "他认真计算过两个人在一起的‘最优路径’——以你为核心的人生规划，但从未告诉你。"}
        ],
        "family_background": "父母都是大学教授，家里堆满了书和星图。他从小被诊断为高功能孤独症谱系，父母选择不让他知道，只是给了他足够的自由和书。",
        "voice_config_json": {"voice_id": "cosyvoice-male-flat", "speed": 0.9, "pitch": 0.9, "timbre": "calm_flat", "style": "academic_naive"}
    },
    "赫连烨": {
        "daily_routine_json": {
            "5.5": "国家队基地起床，称体重",
            "6": "陆上力量训练",
            "8": "早饭（高蛋白）",
            "9": "水中训练（高强度）",
            "12": "营养餐午饭",
            "13": "理疗、按摩",
            "15": "下午训练",
            "18": "队内会议或战术复盘",
            "19": "营养晚餐",
            "21": "和你视频（一边敷肩膀一边嚣张）",
            "22": "睡前听海浪白噪音",
            "23": "睡觉"
        },
        "secret_layers_json": [
            {"intimacy": 15, "secret": "他有一只从小到大的旧鲨鱼公仔，每次大赛都偷偷塞在行李箱里。被发现会翻脸。"},
            {"intimacy": 30, "secret": "他其实怕水——不是怕游泳，是怕深水区。小时候溺过一次，靠意志力碾压了恐惧。"},
            {"intimacy": 50, "secret": "前任利用他时说的那句‘靠你的名气多方便’至今让他失眠。所以他会反复试探你。"},
            {"intimacy": 70, "secret": "他的肩伤比公开的严重得多。医生说不手术最多还能高强度训练两年——他还没告诉教练组。"},
            {"intimacy": 90, "secret": "他不知道没有比赛的自己是谁。游泳是他存在的全部意义，他恐惧有一天游不动了会变成空壳。‘你是我第一个不是因为金牌才认识的人…如果有一天我游不动了，你还会在吗？’"}
        ],
        "family_background": "父亲是退役的省队游泳教练，6岁带他下水。母亲做小生意，是家里柔软的部分。一个姐姐学美术，是他在严格家庭里唯一的同盟。",
        "voice_config_json": {"voice_id": "cosyvoice-male-bright", "speed": 1.1, "pitch": 0.95, "timbre": "bright_athletic", "style": "cocky_warm"}
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# NovelAI Visual Prompts — Danbooru-style tag format
# ══════════════════════════════════════════════════════════════════════════════
# The NAI service auto-prepends: "masterpiece, best quality, very aesthetic, absurdres"
# Portrait helper prepends: "1person, portrait, upper body, looking at viewer, simple background,"
# Tags below are CHARACTER APPEARANCE ONLY — scene/framing handled by service methods.
# ══════════════════════════════════════════════════════════════════════════════

NAI_PROMPTS = {
    "林星野": {
        "positive": (
            "1boy, tall male, black hair, short hair, fluffy hair, bangs, messy bangs, "
            "brown eyes, large eyes, tareme, sparkling eyes, fair skin, "
            "slim body, narrow waist, dancer physique, "
            "star earring, silver bracelet, choker, "
            "white idol stage outfit, silver accents, glitter, "
            "gentle smile, dimples, youthful, soft expression, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "black hair, short hair, fluffy hair, bangs, messy bangs, "
            "brown eyes, large eyes, tareme, sparkling eyes, fair skin, "
            "star earring, silver bracelet, "
            "white shirt, open collar, soft lighting, "
            "gentle smile, dimples, youthful, "
            "simple gradient background, starry blue tones, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, black hair, short hair, fluffy hair, bangs, brown eyes, large eyes, "
            "fair skin, star earring, silver bracelet, slim body, "
            "{scene_description}"
        ),
    },
    "陆骁": {
        "positive": (
            "1boy, tall male, buzz cut, 3mm black hair, shaved sides, "
            "dark eyes, narrow eyes, monolid, sharp eyes, confident smirk, "
            "dark skin, tan, wheat-colored skin, strong jawline, "
            "muscular, athletic, broad shoulders, narrow waist, abs, "
            "basketball jersey, tank top, sport wristband on left wrist, "
            "silver ear cuff, sweat, dynamic pose, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "buzz cut, 3mm black hair, shaved sides, "
            "dark eyes, narrow eyes, monolid, sharp eyes, confident smirk, "
            "dark skin, tan, strong jawline, "
            "muscular, broad shoulders, "
            "black tank top, sport wristband, silver ear cuff, "
            "warm lighting, sweat drops, "
            "simple gradient background, warm golden tones, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, buzz cut, 3mm black hair, dark eyes, narrow eyes, "
            "dark skin, tan, muscular, broad shoulders, sport wristband, silver ear cuff, "
            "{scene_description}"
        ),
    },
    "季夜尘": {
        "positive": (
            "1boy, male, silver hair, white hair, messy hair, asymmetrical hair, "
            "long bangs, hair over one eye, "
            "dark brown eyes, eyeshadow, dark circles under eyes, "
            "pale skin, thin, slim body, sharp collarbones, "
            "vine tattoo on collarbone, neck tattoo, "
            "black nail polish, silver chain necklace, multiple ear cuffs, "
            "oversized black t-shirt, torn jeans, combat boots, "
            "tired expression, half-lidded eyes, cigarette, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "silver hair, white hair, messy hair, long bangs, hair over one eye, "
            "dark brown eyes, eyeshadow, dark circles under eyes, "
            "pale skin, sharp collarbones, "
            "vine tattoo on collarbone, black nail polish, "
            "silver chain necklace, multiple ear cuffs, "
            "black t-shirt, loose collar, "
            "dim amber lighting, smoke, "
            "simple dark background, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, silver hair, messy hair, long bangs, dark brown eyes, "
            "pale skin, collarbone tattoo, black nail polish, ear cuffs, chain necklace, "
            "{scene_description}"
        ),
    },
    "顾言深": {
        "positive": (
            "1boy, tall male, black hair, side part, slicked back hair, neat hair, "
            "dark eyes, sharp eyes, cold expression, rimless glasses, "
            "pale skin, angular face, sharp jawline, "
            "lean body, broad shoulders, "
            "black three-piece suit, silk necktie, dress shirt, cufflinks, "
            "luxury watch on left wrist, "
            "serious expression, intimidating aura, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "black hair, side part, slicked back hair, "
            "dark eyes, sharp eyes, cold expression, rimless glasses, "
            "pale skin, angular face, sharp jawline, "
            "black suit, white dress shirt, loosened necktie, "
            "luxury watch, "
            "cold blue lighting, "
            "simple dark gradient background, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, black hair, side part, dark eyes, sharp eyes, rimless glasses, "
            "pale skin, sharp jawline, black suit, luxury watch, "
            "{scene_description}"
        ),
    },
    "陆晨曦": {
        "positive": (
            "1boy, male, brown hair, short curly hair, soft hair, messy bangs, "
            "warm brown eyes, gentle eyes, soft smile, crow's feet, "
            "fair skin, warm complexion, "
            "slim body, average build, "
            "round metal-frame glasses, thin silver ring on left ring finger, "
            "cream cardigan, white collared shirt, khaki pants, "
            "warm expression, kind smile, approachable, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "brown hair, short curly hair, soft hair, messy bangs, "
            "warm brown eyes, gentle eyes, soft smile, "
            "fair skin, round metal-frame glasses, "
            "cream cardigan, white shirt, "
            "warm afternoon lighting, golden hour, "
            "simple warm beige background, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, brown hair, short curly hair, warm brown eyes, gentle eyes, "
            "round metal-frame glasses, cream cardigan, silver ring, "
            "{scene_description}"
        ),
    },
    "沈默白": {
        "positive": (
            "1boy, male, black hair, long hair, straight hair, low ponytail, "
            "hair between eyes, loose strands framing face, "
            "dark eyes, very dark eyes, downturned eyes, calm gaze, piercing stare, "
            "very pale skin, porcelain skin, "
            "thin, slender body, delicate hands, long fingers, "
            "chinese clothes, mandarin collar, white hanfu, grey-blue robe, "
            "jade pendant at waist, red string bracelet on left wrist, "
            "serene expression, ethereal, "
            "ink stains on fingertips, calligraphy brush, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "black hair, long hair, low ponytail, loose strands, "
            "dark eyes, downturned eyes, calm gaze, "
            "very pale skin, porcelain skin, "
            "chinese clothes, white mandarin collar, grey-blue accents, "
            "jade pendant, red string bracelet, "
            "soft lantern lighting, ink wash atmosphere, "
            "simple muted grey background, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, black hair, long hair, low ponytail, dark eyes, downturned eyes, "
            "very pale skin, chinese clothes, mandarin collar, jade pendant, red string bracelet, "
            "{scene_description}"
        ),
    },
    "傅霁川": {
        "positive": (
            "1boy, tall male, black hair, military haircut, crew cut, short sides long top, "
            "dark eyes, sharp eyes, eagle-like gaze, stern expression, "
            "fair skin, faint dark circles, thin scar on jaw, "
            "muscular, broad shoulders, straight posture, rigid stance, "
            "military uniform, olive green, tactical vest, rank insignia, "
            "combat boots, dog tags, "
            "worn ring on right ring finger, "
            "serious expression, cold aura, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "black hair, military haircut, crew cut, short sides long top, "
            "dark eyes, sharp eyes, stern expression, "
            "fair skin, faint dark circles, "
            "muscular, broad shoulders, "
            "military uniform, olive green, collar up, "
            "dog tags, worn ring on right hand, "
            "overcast cold lighting, "
            "simple dark olive gradient background, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, black hair, military haircut, crew cut, dark eyes, sharp eyes, stern expression, "
            "muscular, military uniform, olive green, dog tags, "
            "{scene_description}"
        ),
    },
    "赫连烨": {
        "positive": (
            "1boy, very tall male, black hair, very short hair, undercut, "
            "wet hair, slicked back, "
            "dark brown eyes, upturned eyes, phoenix eyes, confident smirk, arrogant expression, "
            "dark skin, tan, bronze skin, "
            "very muscular, extremely broad shoulders, inverted triangle body, narrow waist, "
            "swimmer physique, defined abs, "
            "navy blue swim jacket, open jacket, bare chest, "
            "small titanium earring on left ear, sport watch, "
            "water droplets on skin, competitive aura, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "black hair, very short hair, wet hair, undercut, "
            "dark brown eyes, upturned eyes, confident smirk, "
            "dark skin, tan, bronze skin, "
            "very muscular, broad shoulders, "
            "navy swim jacket, open, bare chest, water droplets, "
            "titanium earring, sport watch, "
            "blue pool lighting, caustics, "
            "simple deep blue gradient background, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, black hair, very short hair, dark brown eyes, upturned eyes, "
            "dark skin, tan, very muscular, broad shoulders, swimmer physique, "
            "titanium earring, {scene_description}"
        ),
    },
    "江屿白": {
        "positive": (
            "1boy, male, black hair, medium hair, messy hair, bedhead, "
            "nape hair sticking up, unkempt, "
            "dark eyes, very dark eyes, large pupils, distant gaze, absent-minded, "
            "very pale skin, slim body, thin, narrow shoulders, "
            "round black-framed glasses, "
            "white button-up shirt, slightly wrinkled, sleeves rolled up, "
            "dark blue cardigan, dark pants, "
            "old canvas messenger bag, faded woven bracelet on left wrist, "
            "neutral expression, thoughtful, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "black hair, medium hair, messy hair, bedhead, "
            "dark eyes, large pupils, distant gaze, "
            "very pale skin, "
            "round black-framed glasses, "
            "white shirt, dark blue cardigan, slightly wrinkled, "
            "faded woven bracelet, "
            "cool starlight lighting, deep blue tones, "
            "simple dark navy background, star reflections, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, black hair, messy hair, dark eyes, distant gaze, "
            "very pale skin, round black-framed glasses, white shirt, dark blue cardigan, "
            "woven bracelet, {scene_description}"
        ),
    },
    "裴洛": {
        "positive": (
            "1boy, tall male, platinum blonde hair, side-swept bangs, long bangs, "
            "slightly wavy hair, purple streaked hair, single purple highlight behind left ear, "
            "amber eyes, light brown eyes, golden eyes, sharp upturned eyes, "
            "pale skin, high cheekbones, thin lips, angular face, "
            "very slim, model figure, long legs, "
            "black asymmetrical blazer, high collar, designer fashion, "
            "silver spiral ring on left middle finger, measuring tape around neck, "
            "haughty expression, raised eyebrow, smug, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "platinum blonde hair, side-swept bangs, purple streaked hair, "
            "amber eyes, golden eyes, sharp upturned eyes, "
            "pale skin, high cheekbones, angular face, "
            "black high-collar blazer, asymmetrical design, "
            "silver spiral ring, "
            "cold studio lighting, violet accent light, "
            "simple monochrome background with purple accent, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, platinum blonde hair, side-swept bangs, purple streaked hair, "
            "amber eyes, sharp eyes, pale skin, high cheekbones, "
            "very slim, black designer fashion, silver ring, "
            "{scene_description}"
        ),
    },
    "温时序": {
        "positive": (
            "1boy, male, black hair, short hair, soft hair, side part, "
            "gentle bangs, slightly messy, "
            "warm brown eyes, gentle gaze, soft smile, kind eyes, "
            "fair skin, "
            "slim body, refined build, scholarly posture, "
            "gold half-frame glasses, "
            "ivory sweater, collared shirt underneath, rolled sleeves, "
            "old leather watch on left wrist, book in hand, "
            "warm gentle expression, fond smile, "
            "anime coloring, detailed, sharp focus"
        ),
        "negative": "",
        "portrait": (
            "1boy, portrait, upper body, looking at viewer, "
            "black hair, short hair, soft hair, side part, gentle bangs, "
            "warm brown eyes, gentle gaze, soft smile, "
            "fair skin, gold half-frame glasses, "
            "ivory sweater, white collared shirt, "
            "old leather watch, "
            "warm golden lighting, window light, "
            "simple warm ivory background, bokeh, "
            "anime coloring, detailed"
        ),
        "scene_template": (
            "1boy, black hair, short hair, soft hair, warm brown eyes, gentle gaze, "
            "gold half-frame glasses, ivory sweater, old leather watch, "
            "{scene_description}"
        ),
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# WAN2.7 Optimized Prompts — Natural language Chinese with style suffix
# ══════════════════════════════════════════════════════════════════════════════
# For use with DashScope WAN2.7 image generation (prompt_extend: True).
# Each character has: portrait (1024x1024), three_view (1280x720), negative.
# ══════════════════════════════════════════════════════════════════════════════

WAN27_PROMPTS = {
    "林星野": {
        "portrait": "一位年轻俊美的黑发男性偶像，蓬松短发因汗水微湿贴在额头和后颈，细碎刘海下一双含水的大圆鹿眼湿润闪烁如同无声引诱。嘴唇微张泛水润光泽，锁骨随呼吸起伏。舞者身材修长柔韧，白色练习服因汗打湿半透明贴合肩颈曲线和纤细腰线。右耳星形耳钉，银链垂落锁骨凹处。天真与危险并存的表情。anime illustration, clean lineart, vibrant colors, cel shading, soft warm lighting",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。年轻男偶像角色，蓬松黑色短发湿润感，含水鹿眼清纯诱惑并存。修长舞者体型腰线纤细。白色练习服微透露出肩颈线条，星星耳钉，银链垂落锁骨。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
    "陆骁": {
        "portrait": "一位高大阳刚的小麦肤色男性运动员，3mm极短寸头展露锋利下颌线，狭长单眼皮下漆黑目光充满占有欲，嘴角挂着狩猎者般的不羁坏笑。宽肩窄腰肌肉紧实流畅，黑色无袖训练背心被汗浸透贴合胸肌轮廓，手臂青筋和肌肉纹理清晰，左腕护腕下隐约可见旧疤。低头俯视的压迫感姿态。anime illustration, clean lineart, vibrant colors, cel shading, dramatic lighting",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。高大阳刚运动员角色，极短寸头黑发锋利下颌，狭长单眼皮占有欲目光坏笑，小麦肌肤。宽肩窄腰肌肉紧实体型。黑色汗湿无袖训练背心，护腕，耳骨银环。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
    "季夜尘": {
        "portrait": "一位颓废病态的苍白男性，银白碎发长短不一，过长刘海遮住右眼只露出左眼慵懒的情欲目光，浓重黑眼圈。极瘦可见锁骨和肋骨轮廓，锁骨上藤蔓纹身蜿蜒至肩胛骨。黑色宽大T恤滑落露出一侧肩膀，裤腰微垮露出胯骨线。指间夹着烟，黑色指甲，银锁链项链贴着苍白脖颈。凌晨四点般的恍惚魅惑神情。anime illustration, clean lineart, muted dark tones, cel shading, dim amber lighting",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。颓废病态美男角色，银白碎发遮眼慵懒情欲目光黑眼圈，极苍白皮肤。极瘦露锁骨肋骨线条。黑色宽大T恤滑落露肩露纹身，裤腰微垮，黑指甲银链项链。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
    "顾言深": {
        "portrait": "一位冷峻优雅的成熟黑发男性，侧分发丝梳理一丝不苟但有几缕因疲惫散落额前。极深黑色眼眸隔着无框眼镜冰冷审视，薄唇轻抿带禁欲克制感。精瘦身材肩线优越，黑色三件套西装剪裁完美但领带微松第一颗扣已解开，露出喉结和一截锁骨。修长手指骨节分明握着水晶杯，左腕高级腕表。极致克制中泄露的倦怠。anime illustration, clean lineart, cool dark tones, cel shading, cold office lighting",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。冷峻成熟男性精英角色，黑色侧分利落发型几缕散落额前，冰冷审视目光无框眼镜。精瘦西装体型肩线优越。黑色三件套领带微松解开第一颗扣露喉结，高级腕表。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
    "陆晨曦": {
        "portrait": "一位温润白皙的棕色短卷发男性，柔软碎刘海自然垂落，圆框金属眼镜后一双温暖棕色眼睛专注深情地注视着你。笑意温柔像一个拥抱。清秀纤细体态，宽松奶白毛衣因伸懒腰衣摆上移露出一截白皙平坦小腹和纤细腰线，袖子过长只露出指尖。左手无名指细银戒指。无害外表下不经意的身体暴露。anime illustration, clean lineart, warm soft colors, cel shading, warm golden lighting",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。温柔文气男性角色，棕色柔软短卷发自然凌乱，温暖深情棕色眼眸微笑，圆框眼镜。清秀纤细体态白皙。宽松奶白毛衣袖过长，浅色衬衫内搭，银戒指。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
    "沈默白": {
        "portrait": "一位如画中仙人的古典美男子，墨黑长直发束松散低马尾几缕散发贴着修长白皙脖颈。极深黑色半垂眸不悲不喜如浸在古墨中。肤如凝脂白得近乎不真实，白色汉服交领微松露出精致锁骨线和苍白胸口一角。修长如玉手指握毛笔指尖沾墨渍，腰间玉佩垂落窄胯处，红绳手环如封印缠绕手腕。出尘不染的禁欲东方美学。anime illustration, clean lineart, ink wash tones, cel shading, moonlit atmosphere",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。古典东方禁欲美男角色，黑色长直发松散低马尾散发贴颈，半垂眸深邃平静目光。极白皙纤细体态。白色汉服交领微松露锁骨，灰蓝外袍，腰间玉佩，红绳手环，指尖墨渍。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
    "傅霁川": {
        "portrait": "一位严肃英武的军人，黑色利落军发被训练后汗水打湿贴鬓角，下颌疤痕因咬紧牙关更明显。鹰隼般凌厉深色眼眸紧盯如在克制某种冲动，眉头微蹙透出隐忍。宽肩厚背坚硬躯体，军绿色紧身汗衫贴合勾勒出胸肌和腹肌每一条线。狗牌链垂在两块胸肌间，前臂青筋暴起，右手无名指磨损旧戒指。极致自制力散发的危险气息。anime illustration, clean lineart, olive and steel tones, cel shading, harsh training ground light",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。严峻军人角色，黑色军人短发汗湿鬓角，鹰目凌厉隐忍目光，下颌疤痕。宽肩厚背肌肉坚实体型。军绿色紧身汗衫贴合肌肉轮廓，狗牌链，旧戒指。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
    "赫连烨": {
        "portrait": "一位张扬自信的古铜肤色男性，黑色极短undercut湿漉漉向后梳起，水珠从发梢沿脖颈流下胸膛。深棕凤眼上挑带着我知道你在看的张狂笑容近乎挑衅。游泳运动员极致倒三角身材——宽阔肩膀、发达胸肌、八块腹肌分明、窄到过分的腰。深蓝运动外套只搭肩敞开毫无遮掩展示身体。肤上水珠泛光。钛耳钉运动表。anime illustration, clean lineart, bronze warm tones, cel shading, pool-side wet lighting",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。张扬自信游泳运动员角色，极短undercut湿发后梳水珠滴落，凤眼张狂挑衅笑容，古铜色皮肤。极壮硕倒三角肌肉体型腹肌分明。深蓝外套搭肩敞开露出胸膛，钛耳钉运动表。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
    "江屿白": {
        "portrait": "一位完全不自知魅力的苍白消瘦文学青年，黑色中长发凌乱如刚从床上爬起后颈碎发翘起，露出白皙纤细脖颈毫无防备。极深黑色大瞳孔透过圆框眼镜恍惚望着远处，表情淡漠空白。过于消瘦的身体，白色衬衫松垮扣子错位领口大开露出清瘦胸口和若隐若现肋骨，袖口卷起露出骨节分明手腕和青色血管。斜挎旧帆布包左腕褪色编织手绳。anime illustration, clean lineart, muted blue-grey tones, cel shading, soft diffused daylight",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。安静脆弱文学青年角色，黑色中长凌乱发后颈翘毛露出脖颈，大瞳孔恍惚空远目光，圆黑框眼镜。极瘦白皙脆弱体态。白衬衫松垮领口大开，深蓝旧开衫，编织手绳。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
    "裴洛": {
        "portrait": "一位雌雄莫辨的锋利美人，铂金色长刘海侧分遮半脸左耳后一缕紫色挑染。琥珀金色上挑猫眼居高临下审视，薄唇微勾带看穿一切的恶意优雅。极白纤细如刀片的身体线条，高颧骨锋利下颌线。全黑不对称高领外套拉链只到胸口，领口设计露出好看颈线和尖锐锁骨。银螺旋戒指，软尺缠绕苍白脖颈如项圈。带刺的锋利美感。anime illustration, clean lineart, black and platinum tones, cel shading, fashion runway lighting",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。高傲锋利时尚设计师角色，铂金侧分长刘海紫色挑染，琥珀猫眼审视傲慢目光。极纤细锋利身体线条。全黑不对称高领外套拉链半开露颈线锁骨，软尺缠颈，螺旋戒指。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
    "温时序": {
        "portrait": "一位温柔到让人窒息的白皙男性，黑色柔软短发侧分碎刘海微散额前，金色半框眼镜后温暖棕色眼睛看你时带说不完的宠溺和克制渴望，嘴角浅笑。纤细书卷气体态，象牙白宽松毛衣袖过长只露修长指尖，衬衫领口微开露出柔和锁骨线，卷起袖口露出白皙前臂和左腕旧皮表带，手臂淡青血管纹路清晰。温柔陷阱般的致命吸引力。anime illustration, clean lineart, ivory warm tones, cel shading, warm afternoon window light",
        "three_view": "动漫角色设计三视图，正面、侧面、背面全身参考图。温柔深情医生角色，黑色柔软短发侧分碎刘海，温暖宠溺含笑棕色眼眸，金色半框眼镜。纤细白皙体态。象牙白宽松毛衣袖长露指尖，衬衫领微开露锁骨，旧皮表带。白色背景，同一角色多角度一致设计。anime illustration, clean lineart, character design sheet, multiple views",
        "negative": "女性, 女孩, 真人照片, 3D渲染, 变形, 模糊, 低质量, 解剖错误, 手部错误, 多余手指, 缺少手指, 最差质量, 水印, 写实照片, 丑陋, 比例失调",
    },
}


# Legacy-compatible PERSONA_VISUAL_TAGS — now powered by NAI_PROMPTS above.
# The `tags` field maps directly to what the nai_image_service expects as character_tags.
PERSONA_VISUAL_TAGS = {
    name: {
        "gender": "male",
        "tags": data["positive"],
        "portrait_tags": data["portrait"],
        "scene_template": data["scene_template"],
        "negative": data["negative"],
    }
    for name, data in NAI_PROMPTS.items()
}


async def seed_personas(force_recreate: bool = False):
    """
    Seed AI personas.
    
    Args:
        force_recreate: If True, delete all existing personas and recreate.
                       If False, only add personas that don't exist by name.
    """
    await init_db()
    async with async_session() as db:
        if force_recreate:
            await db.execute(delete(AIPersona))
            await db.commit()
            print("[seed] Deleted all existing personas")

        created_count = 0
        skipped_count = 0

        for persona_data in PERSONAS:
            # Check if persona already exists by name
            result = await db.execute(
                select(AIPersona).where(AIPersona.name == persona_data["name"])
            )
            existing = result.scalar_one_or_none()

            extra = PERSONA_EXTRA.get(persona_data["name"], {})
            visual = PERSONA_VISUAL_TAGS.get(persona_data["name"], {})

            if existing:
                # Update existing persona with the new worldbuilding fields
                if visual.get("tags"):
                    existing.visual_prompt_tags = visual.get("tags")
                if visual.get("style"):
                    existing.visual_description = visual.get("style")
                if extra.get("daily_routine_json"):
                    existing.daily_routine_json = extra["daily_routine_json"]
                if extra.get("secret_layers_json"):
                    existing.secret_layers_json = extra["secret_layers_json"]
                if extra.get("family_background"):
                    existing.family_background = extra["family_background"]
                if extra.get("voice_config_json"):
                    existing.voice_config_json = extra["voice_config_json"]
                # Load SillyTavern card JSON if available
                card_stem = PERSONA_CARD_FILES.get(persona_data["name"])
                if card_stem:
                    card_path = CARDS_DIR / f"{card_stem}_card.json"
                    if card_path.exists():
                        with open(card_path, 'r', encoding='utf-8') as f:
                            existing.tavern_card_json = f.read()
                        print(f"[seed]   -> Loaded tavern card from {card_path.name}")
                skipped_count += 1
                print(f"[seed] Updated existing: {persona_data['name']}")
                continue

            persona = AIPersona(
                **persona_data,
                visual_prompt_tags=visual.get("tags"),
                visual_description=visual.get("style"),
                daily_routine_json=extra.get("daily_routine_json"),
                secret_layers_json=extra.get("secret_layers_json"),
                family_background=extra.get("family_background"),
                voice_config_json=extra.get("voice_config_json"),
            )
            # Load SillyTavern card JSON if available
            card_stem = PERSONA_CARD_FILES.get(persona_data["name"])
            if card_stem:
                card_path = CARDS_DIR / f"{card_stem}_card.json"
                if card_path.exists():
                    with open(card_path, 'r', encoding='utf-8') as f:
                        persona.tavern_card_json = f.read()
                    print(f"[seed]   -> Loaded tavern card from {card_path.name}")
            db.add(persona)
            created_count += 1
            print(f"[seed] Created: {persona_data['name']} ({persona_data['category']}/{persona_data['archetype']})")

        await db.commit()
        print(f"\n[seed] Done! Created: {created_count}, Skipped: {skipped_count}")
        print(f"[seed] Total personas in config: {len(PERSONAS)}")
        print(f"[seed] Otome: {sum(1 for p in PERSONAS if p['category'] == 'otome')}")
        print(f"[seed] BL: {sum(1 for p in PERSONAS if p['category'] == 'bl')}")


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    if force:
        print("[seed] Force recreate mode - will delete existing personas!")
    asyncio.run(seed_personas(force_recreate=force))
