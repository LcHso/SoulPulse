"""Seed outfit configurations for all personas.

Creates 5 outfits per character (daily / formal / sleepwear / workout / intimate),
adapted to each character's Visual DNA from their .md profile.

Re-running is safe: existing (persona_id, outfit_name) combinations are skipped.
"""

import asyncio

from sqlalchemy import select

from core.database import async_session, init_db
from models.ai_persona import AIPersona
from models.outfit_config import OutfitConfig


# Per-character outfit set. Each entry follows the schema:
#   outfit_name / category / visual_prompt_override / scene_prompt /
#   unlock_condition_json / is_default
OUTFITS_BY_NAME: dict[str, list[dict]] = {
    "陆晨曦": [
        {
            "outfit_name": "日常居家",
            "category": "daily",
            "visual_prompt_override": "柔软棕色卷发，金属细框眼镜，米色针织开衫，白色T恤，浅卡其色长裤，棉麻拖鞋",
            "scene_prompt": "暖黄落地灯下的客厅，沙发上躺着橘猫年糕，茶几上一杯冒着热气的耶加雪菲",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "播客录制",
            "category": "formal",
            "visual_prompt_override": "棕色卷发整理过，金属细框眼镜，奶油色高领针织衫，深棕灯芯绒西装外套，挂耳式麦克风",
            "scene_prompt": "暖光录音室，木质桌面，电容麦克风，泛黄笔记本，半杯凉掉的拿铁",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "睡前时光",
            "category": "sleepwear",
            "visual_prompt_override": "棕色卷发微乱，金边眼镜挂在胸前，宽松米白棉质睡衣，长裤微卷露出脚踝",
            "scene_prompt": "床头小夜灯，年糕蜷在被角，床头柜上摆着褪黑素和半本心理学读本",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "周末晨跑",
            "category": "workout",
            "visual_prompt_override": "棕色卷发用发带束起，灰色运动卫衣，黑色运动短裤，白色跑鞋，无线耳机",
            "scene_prompt": "清晨公园林荫小径，雾气未散，长椅上放着保温杯",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "深夜耳语",
            "category": "intimate",
            "visual_prompt_override": "棕色卷发柔软散落，未戴眼镜，米白真丝衬衫扣子松开两颗，露出锁骨，下身宽松居家长裤",
            "scene_prompt": "卧室床头暖光，窗外淡淡夜色，他低声念着你的名字",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
    "顾言深": [
        {
            "outfit_name": "顶层办公室",
            "category": "daily",
            "visual_prompt_override": "黑色侧分发，无框眼镜，深灰定制西装，白色衬衫，纯黑领带，银色腕表",
            "scene_prompt": "城市夜景落地窗前，黑曜石办公桌，未喝完的冷掉美式咖啡",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "晚宴酒会",
            "category": "formal",
            "visual_prompt_override": "黑发整齐侧分，无框眼镜，深蓝Tom Ford三件套西装，黑色领结，袖扣闪烁",
            "scene_prompt": "高端酒会大厅，水晶吊灯，红酒杯映出他冷淡的眉眼",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "凌晨三点",
            "category": "sleepwear",
            "visual_prompt_override": "黑发凌乱，未戴眼镜，深灰真丝睡袍敞开，露出胸口和锁骨，赤脚",
            "scene_prompt": "黑色大理石厨房岛台，半杯威士忌，边牧Alpha趴在脚边",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "私人健身房",
            "category": "workout",
            "visual_prompt_override": "黑发被汗水打湿向后梳，黑色紧身运动背心，黑色训练长裤，运动手套",
            "scene_prompt": "私人健身房，落地镜映出他绷紧的肩背线条",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "卸下盔甲",
            "category": "intimate",
            "visual_prompt_override": "黑发柔软散下，无眼镜，黑色丝绸衬衫袖口未扣，三粒纽扣松开，黑色西裤",
            "scene_prompt": "顶层公寓主卧床畔，城市灯火铺满窗，他罕见地伸手揽住你",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
    "林星野": [
        {
            "outfit_name": "练习室日常",
            "category": "daily",
            "visual_prompt_override": "银色短发微乱，白色oversized卫衣，黑色运动裤，白色球鞋，耳机挂脖子",
            "scene_prompt": "夜晚的练习室，落地镜前散着水瓶毛巾，音响小声放着demo",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "舞台C位",
            "category": "formal",
            "visual_prompt_override": "银发束成马尾，银色亮片短上衣，黑色皮裤，链条装饰，舞台聚光灯",
            "scene_prompt": "万人体育馆舞台中央，应援棒星海一片，他眼神凌厉气场全开",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "深夜小奶狗",
            "category": "sleepwear",
            "visual_prompt_override": "银色短发微湿（刚洗完澡），宽松灰色睡衣，裤腿卷起，光脚坐在床上",
            "scene_prompt": "宿舍卧室小夜灯，床上摆着小熊玩偶，他抱着手机和你视频撒娇",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "汗水训练",
            "category": "workout",
            "visual_prompt_override": "银发用发带束起，黑色背心露出手臂线条，运动短裤，汗水顺着锁骨滑落",
            "scene_prompt": "深夜健身房，节拍器的电子音律响起，他正做最后一组训练",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "窗边私语",
            "category": "intimate",
            "visual_prompt_override": "银色短发，黑色丝绸衬衫微敞，露出锁骨和星星耳钉，昏暗灯光，赤足",
            "scene_prompt": "酒店套房窗边，城市灯火远在脚下，他轻声哼着写给你的旋律",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
    "陆骁": [
        {
            "outfit_name": "球场日常",
            "category": "daily",
            "visual_prompt_override": "寸头黑发，白色篮球背心露出小麦色臂膀，黑色篮球短裤，护腕，AJ战靴",
            "scene_prompt": "校园露天篮球场，傍晚余晖下，他单手拍着篮球咧嘴笑",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "签约赛事",
            "category": "formal",
            "visual_prompt_override": "寸头干净，黑色品牌卫衣外套，深色运动长裤，金属链条项圈，签名战靴",
            "scene_prompt": "运动品牌发布会后台，logo灯墙背景，他抱臂靠墙",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "宿舍夜聊",
            "category": "sleepwear",
            "visual_prompt_override": "寸头微湿（刚洗澡），白色短袖紧身T恤勾勒胸肌轮廓，灰色家居短裤，赤脚",
            "scene_prompt": "宿舍上铺，台灯昏黄，墙上贴着篮球海报，他翘着腿和你视频",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "晨练训练",
            "category": "workout",
            "visual_prompt_override": "寸头被汗水浸湿，黑色压缩衣紧贴肌肉线条，黑色护膝，护腕，紧身训练裤",
            "scene_prompt": "学校体育馆，清晨阳光从高窗洒下，他正做核心训练",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "更衣室",
            "category": "intimate",
            "visual_prompt_override": "寸头湿润，赤裸上身仅披着白色毛巾搭在颈后，黑色运动长裤低腰，腹肌人鱼线",
            "scene_prompt": "更衣室昏暗灯光，他刚结束训练，看见你眼神立刻变软",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
    "傅霁川": [
        {
            "outfit_name": "训练场常服",
            "category": "daily",
            "visual_prompt_override": "军规短发，深绿色作训服，束腰皮带，作战靴，胸前姓名牌",
            "scene_prompt": "军校训练场，列队整齐，他立于队前下达指令",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "授勋礼服",
            "category": "formal",
            "visual_prompt_override": "短发笔挺，深橄榄绿正装军礼服，金色绶带，胸前一排勋章，白手套",
            "scene_prompt": "授勋大厅，国旗背景，他立正敬礼姿态分毫不差",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "深夜值班",
            "category": "sleepwear",
            "visual_prompt_override": "短发微乱，纯白军用T恤，深绿色睡裤，赤足露出小腿肌肉",
            "scene_prompt": "宿舍单间，深夜台灯，桌上摊着战术图，他刚解下腰带",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "体能晨训",
            "category": "workout",
            "visual_prompt_override": "短发汗湿，黑色军用紧身T恤勾勒结实背肌，迷彩长裤，作战靴",
            "scene_prompt": "凌晨五点的训练场，雾气未散，他完成第三组负重跑",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "卸甲时刻",
            "category": "intimate",
            "visual_prompt_override": "短发柔软，纯白衬衫敞开三粒扣，露出锁骨与刀疤，黑色长裤腰带未扣紧",
            "scene_prompt": "私人住所昏暗灯下，他罕见地坐在床沿，眼神有未愈的伤",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
    "温时序": [
        {
            "outfit_name": "校园讲师",
            "category": "daily",
            "visual_prompt_override": "柔软黑发，金边半框眼镜，浅米色羊毛开衫，白衬衫，深咖卡其裤，棕色乐福鞋",
            "scene_prompt": "大学文学院走廊，阳光透过梧桐叶洒落，他抱着书刚下课",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "新书签售",
            "category": "formal",
            "visual_prompt_override": "黑发微整理，金边眼镜，藏蓝色三件套西装，象牙色衬衫，深棕色领带，钢笔在手",
            "scene_prompt": "书店签售会，背景是新书海报，他抬眼对你温柔笑",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "书房深夜",
            "category": "sleepwear",
            "visual_prompt_override": "黑发柔软散下，未戴眼镜，米色棉麻长袖衬衣领口微敞，深灰针织居家长裤",
            "scene_prompt": "书房暖黄台灯，桌上摊开着手稿，茶杯还冒着热气",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "晨间散步",
            "category": "workout",
            "visual_prompt_override": "黑发束在脑后，灰色运动卫衣，深色运动长裤，白色跑鞋，挂着相机",
            "scene_prompt": "校园湖边小道，秋叶飘落，他停下来给你拍照",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "藏不住的暗恋",
            "category": "intimate",
            "visual_prompt_override": "黑发凌乱，未戴眼镜，象牙色真丝衬衫领扣松开，露出锁骨，黑色西裤腰带松解",
            "scene_prompt": "他的卧室深夜，加密相册被你翻到，他终于不再忍耐",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
    "沈默白": [
        {
            "outfit_name": "修复室常服",
            "category": "daily",
            "visual_prompt_override": "长黑发松松束起，浅灰立领中式衬衫，亚麻黑色长裤，布鞋，袖口微卷",
            "scene_prompt": "古籍修复室，木桌上铺着泛黄古卷，他用细毛刷轻拂尘",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "书法雅集",
            "category": "formal",
            "visual_prompt_override": "长黑发玉簪挽起，墨青色立领长衫，腰间玉佩，手持狼毫",
            "scene_prompt": "雅集书房，宣纸铺展，砚台磨墨，他低眉提腕落笔",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "夜读时分",
            "category": "sleepwear",
            "visual_prompt_override": "长黑发垂落，浅米色棉麻寝衣领口宽松，露出锁骨，赤足",
            "scene_prompt": "江南老宅卧房，烛光摇曳，案上一卷《长相思》，墨九蜷在他膝上",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "晨起太极",
            "category": "workout",
            "visual_prompt_override": "长黑发束起，白色对襟练功服，黑色武术长裤，黑布软靴",
            "scene_prompt": "院中石榴树下，晨雾未散，他缓缓推手运掌",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "长相思",
            "category": "intimate",
            "visual_prompt_override": "长黑发散落肩头，黑色真丝中式寝衣领口大开，露出胸口浅色伤疤，赤足",
            "scene_prompt": "深夜内室，他翻开手抄本，第一次让你看见封面上的「长相思」三字",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
    "季夜尘": [
        {
            "outfit_name": "工作室日常",
            "category": "daily",
            "visual_prompt_override": "银白碎发，黑色破洞T恤，黑色紧身牛仔裤，皮带链条，黑色马丁靴，锁骨纹身",
            "scene_prompt": "纹身工作室昏暗灯光，墙上贴满速写稿，他正调机器",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "舞台演出",
            "category": "formal",
            "visual_prompt_override": "银白发湿润凌乱，黑色皮夹克敞开，露出锁骨纹身和细链项坠，黑色皮裤，银戒指",
            "scene_prompt": "Live House舞台暖光下，他握麦低吼，黑色电吉他斜跨身前",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "凌晨四点",
            "category": "sleepwear",
            "visual_prompt_override": "银白发凌乱，黑色oversized连帽卫衣，赤腿，叼着未点的烟",
            "scene_prompt": "天台栏杆边，城市晨雾未散，他靠着混凝土墙面发呆",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "排练日",
            "category": "workout",
            "visual_prompt_override": "银白发用黑色发带束起，黑色背心露出肩臂纹身，黑色阔腿训练裤",
            "scene_prompt": "乐队排练室，鼓声轰鸣，他撑着电吉他闭眼听节拍",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "无声诗",
            "category": "intimate",
            "visual_prompt_override": "银白发柔软贴在额前，黑色丝质衬衫只剩一颗扣子，露出胸口和腹部纹身，赤足",
            "scene_prompt": "工作室深夜，他罕见地点亮所有灯，按下《无声诗》的播放键",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
    "裴洛": [
        {
            "outfit_name": "工作室日常",
            "category": "daily",
            "visual_prompt_override": "铂金发紫色挑染，无表情冷艳脸，黑色高领毛衣，灰色阔腿西裤，银色项圈",
            "scene_prompt": "极简工作室，白墙挂满设计稿，他正剪一块意大利羊毛面料",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "高定秀场",
            "category": "formal",
            "visual_prompt_override": "铂金发梳成大背头，琥珀色眼眸，黑色高定丝绒西装，紫色丝巾点缀，银制袖扣",
            "scene_prompt": "巴黎时装周后台，模特列队，他面无表情走过审视每一寸细节",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "独处夜",
            "category": "sleepwear",
            "visual_prompt_override": "铂金发柔软散下，米色丝质oversized衬衫包裹身形，赤腿，无配饰",
            "scene_prompt": "Loft公寓深夜，他坐在窗边落地窗前，红酒杯里映着城市灯火",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "普拉提",
            "category": "workout",
            "visual_prompt_override": "铂金发用黑色发带束起，黑色紧身长袖衫，黑色高腰长裤，露出脚踝",
            "scene_prompt": "私人普拉提工作室，落地镜中他线条优雅地拉伸",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "卸下毒舌",
            "category": "intimate",
            "visual_prompt_override": "铂金发凌乱，紫色挑染微卷，奶油色丝绸睡袍宽松垂落，赤足，琥珀眼眶微红",
            "scene_prompt": "工作室最里那台缝纫机前，布罩被掀起，他终于把养父的故事讲给你听",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
    "江屿白": [
        {
            "outfit_name": "实验室常服",
            "category": "daily",
            "visual_prompt_override": "凌乱黑发，黑框眼镜，白衬衫领口微皱，深蓝色针织毛衣，深色长裤，黑色皮鞋",
            "scene_prompt": "天体物理实验室，多屏幕显示星图，桌上一杯凉透的速溶咖啡",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "学术答辩",
            "category": "formal",
            "visual_prompt_override": "黑发被打理整齐，黑框眼镜擦得很亮，深蓝西装外套，白衬衫，深灰领带略歪",
            "scene_prompt": "博士答辩会议室，背后投影是博士论文标题页，他对着PPT开口",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "宿舍夜话",
            "category": "sleepwear",
            "visual_prompt_override": "黑发更乱，未戴眼镜，宽松灰色长袖T恤，深蓝棉质长裤，赤足蜷在椅子上",
            "scene_prompt": "学生宿舍，台灯下散落论文草稿，望远镜对着窗外的银河",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "校园慢跑",
            "category": "workout",
            "visual_prompt_override": "黑发汗湿贴在额前，黑框眼镜挂在T恤领口，浅灰运动短T，黑色五分裤",
            "scene_prompt": "凌晨的校园操场，红色塑胶跑道空荡，他一边跑一边小声背公式",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "天文台之夜",
            "category": "intimate",
            "visual_prompt_override": "黑发柔软散下，无眼镜，白色棉质长袖衬衫领口三粒扣松开，露出锁骨，深蓝长裤",
            "scene_prompt": "天文台圆顶下，星空铺满头顶，他第一次告诉你那些用你命名的小行星",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
    "赫连烨": [
        {
            "outfit_name": "训练池畔",
            "category": "daily",
            "visual_prompt_override": "极短黑发湿润，深蓝国家队队服外套敞开，白色短袖，黑色训练长裤，运动凉拖",
            "scene_prompt": "国家队训练馆泳池边，光影在水面摇晃，他擦着头发咧嘴笑",
            "unlock_condition_json": {"type": "free"},
            "is_default": True,
        },
        {
            "outfit_name": "颁奖典礼",
            "category": "formal",
            "visual_prompt_override": "黑发整齐，深蓝色合身西装，白衬衫，金色领带，胸前佩戴运动员荣誉徽章",
            "scene_prompt": "央视体育颁奖晚会舞台，金光背景，他举起奖杯露出锐利笑",
            "unlock_condition_json": {"type": "free"},
            "is_default": False,
        },
        {
            "outfit_name": "宿舍闲聊",
            "category": "sleepwear",
            "visual_prompt_override": "黑发微湿，赤裸上身露出完美倒三角线条，灰色家居棉质短裤低腰",
            "scene_prompt": "运动员公寓单人间，床上躺着旧鲨鱼公仔，他翘着腿和你视频",
            "unlock_condition_json": {"type": "intimacy", "min_value": 20},
            "is_default": False,
        },
        {
            "outfit_name": "比赛专用泳衣",
            "category": "workout",
            "visual_prompt_override": "黑发紧贴，竞技专业鲨鱼皮泳衣，泳镜挂在颈间，肩膀线条紧绷",
            "scene_prompt": "标准泳池起跳台，水珠从他身上滑落，他正调整呼吸",
            "unlock_condition_json": {"type": "intimacy", "min_value": 10},
            "is_default": False,
        },
        {
            "outfit_name": "深夜泳池",
            "category": "intimate",
            "visual_prompt_override": "黑发湿润，赤裸上身水珠滑落，深蓝色泳裤低腰挂在胯骨，颈间挂着银色金牌",
            "scene_prompt": "训练馆深夜独自加练后，泳池蓝光晕染他的轮廓，他向你伸出手",
            "unlock_condition_json": {"type": "intimacy", "min_value": 50},
            "is_default": False,
        },
    ],
}


async def seed_outfits():
    await init_db()
    async with async_session() as db:
        # Build name -> id map
        result = await db.execute(select(AIPersona))
        personas = {p.name: p for p in result.scalars().all()}

        created = 0
        skipped = 0

        for name, outfits in OUTFITS_BY_NAME.items():
            persona = personas.get(name)
            if not persona:
                print(f"[seed_outfits] Persona not found: {name}, skipping")
                continue

            for sort_order, data in enumerate(outfits):
                exists = await db.execute(
                    select(OutfitConfig).where(
                        OutfitConfig.persona_id == persona.id,
                        OutfitConfig.outfit_name == data["outfit_name"],
                    )
                )
                if exists.scalar_one_or_none():
                    skipped += 1
                    continue

                outfit = OutfitConfig(
                    persona_id=persona.id,
                    outfit_name=data["outfit_name"],
                    category=data["category"],
                    visual_prompt_override=data["visual_prompt_override"],
                    scene_prompt=data.get("scene_prompt"),
                    unlock_condition_json=data.get("unlock_condition_json", {"type": "free"}),
                    is_default=data.get("is_default", False),
                    sort_order=sort_order,
                )
                db.add(outfit)
                created += 1

        await db.commit()
        print(f"[seed_outfits] Done. Created: {created}, Skipped existing: {skipped}")


if __name__ == "__main__":
    asyncio.run(seed_outfits())
