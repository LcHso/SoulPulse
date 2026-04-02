# SoulPulse 项目文档

## 项目概述

SoulPulse 是一款具有情感智能的 AI 伴侣聊天应用。用户可以与拥有持久记忆、情绪状态和主动消息能力的 AI 角色进行互动。

### 核心特性

- **AI 角色系统**：多个独特的 AI 角色，每个都有独特的性格、背景和视觉形象
- **情感智能**：AI 角色具有多维情绪状态（能量、愉悦度、激活度、思念、安全感）
- **持久记忆**：AI 角色能记住用户的个人信息、偏好和过往对话
- **社交边界**：基于亲密度等级的动态社交边界系统
- **主动关怀**：AI 角色会主动发送关怀消息
- **视觉一致性**：使用面部参考技术确保角色图片一致性

---

## 技术栈

### 后端
- **Python 3.11+**：主要开发语言
- **FastAPI**：异步 Web 框架
- **SQLAlchemy (async)**：异步 ORM
- **SQLite**：关系型数据库
- **ChromaDB**：向量数据库（记忆存储）

### 前端
- **Flutter 3.x**：跨平台 UI 框架
- **Riverpod**：状态管理
- **go_router**：路由管理

### AI 服务
- **阿里云 DashScope**：大语言模型 API
- **Qwen-Max**：对话生成模型
- **Qwen-Character**：角色扮演模型
- **Wanx**：图片/视频生成模型

---

## 项目结构

```
SoulPulse/
├── backend/                    # 后端服务
│   ├── main.py                # FastAPI 应用入口
│   ├── api/                   # API 端点
│   │   └── endpoints/         # 各功能模块端点
│   │       ├── auth.py       # 认证相关
│   │       ├── chat.py       # 聊天相关
│   │       ├── feed.py       # 信息流相关
│   │       ├── admin.py      # 管理后台
│   │       └── ...
│   ├── services/              # 业务逻辑层
│   │   ├── chat_service.py   # 聊天编排
│   │   ├── aliyun_ai_service.py  # AI 服务
│   │   ├── image_gen_service.py  # 图片生成
│   │   ├── memory_service.py # 记忆管理
│   │   ├── emotion_engine.py # 情绪引擎
│   │   └── ...
│   ├── models/                # 数据模型
│   │   ├── user.py           # 用户模型
│   │   ├── ai_persona.py     # AI 角色模型
│   │   ├── post.py           # 帖子模型
│   │   ├── chat_message.py   # 聊天消息模型
│   │   ├── emotion_state.py  # 情绪状态模型
│   │   └── ...
│   ├── core/                  # 核心配置
│   │   ├── config.py         # 应用配置
│   │   ├── database.py       # 数据库连接
│   │   ├── security.py       # 安全认证
│   │   └── ws_manager.py     # WebSocket 管理
│   └── scripts/               # 定时任务脚本
│       ├── emotion_scheduler.py   # 情绪调度器
│       ├── post_scheduler.py      # 帖子生成器
│       └── ...
│
├── frontend/                  # 前端应用
│   └── lib/
│       ├── main.dart          # 应用入口
│       ├── core/              # 核心模块
│       │   ├── api/          # API 客户端
│       │   ├── providers/    # Riverpod Providers
│       │   ├── router/       # 路由配置
│       │   └── theme/        # 主题配置
│       └── features/          # 功能页面
│           ├── auth/         # 认证相关
│           ├── chat/         # 聊天页面
│           ├── feed/         # 信息流
│           ├── profile/      # 个人中心
│           └── admin/        # 管理后台
│
└── docs/                      # 文档目录
```

---

## 核心系统详解

### 1. 社交边界系统（Social Boundary System）

基于用户与 AI 角色的亲密度等级，动态调整 AI 的行为边界。

#### 亲密度等级

| 等级 | 名称 | 亲密度范围 | 行为特征 |
|------|------|-----------|----------|
| 1 | 陌生人 | 0-3 | 冷淡、简短回复、不使用昵称 |
| 2 | 熟人 | 3-5 | 礼貌、适度交流、禁用亲昵称呼 |
| 3 | 朋友 | 5-7 | 温暖、分享日常、可使用"你" |
| 4 | 密友 | 7-9 | 亲密、情感分享、可使用昵称 |
| 5 | 挚爱 | 9-10 | 深情、无限制表达、完全开放 |

#### 关键实现
- **禁用称呼列表**：低亲密度时禁止使用"宝贝"、"亲爱的"等
- **回复长度限制**：陌生人级别回复不超过 20 字
- **话题限制**：低亲密度禁止涉及情感话题

### 2. 情绪引擎（Emotion Engine）

多维情绪状态机，驱动 AI 的行为表现。

#### 情绪维度

| 维度 | 范围 | 说明 |
|------|------|------|
| Energy（能量） | 0-100 | 活跃程度，影响回复长度 |
| Pleasure（愉悦度） | -1.0 到 1.0 | 正向/负向情绪 |
| Activation（激活度） | -1.0 到 1.0 | 情绪强度 |
| Longing（思念） | 0.0 到 1.0 | 对用户的思念程度 |
| Security（安全感） | -1.0 到 1.0 | 关系的稳定感 |

#### 情绪变化
- **时间衰减**：随时间自动变化（能量恢复、思念增加等）
- **交互影响**：聊天、点赞、评论等行为影响情绪
- **关怀检测**：检测用户的关怀用语触发特殊效果

### 3. 记忆系统（Memory System）

双重存储架构，实现长期记忆和语义检索。

#### 存储架构
- **SQLite**：关系存储，存储记忆元数据
- **ChromaDB**：向量存储，支持语义检索

#### 记忆类型
- **事实记忆（fact）**：用户的个人信息、偏好
- **情感记忆（emotion）**：用户的情感经历、心情

#### 亲密度门控
- **Lv 0-5**：仅检索事实记忆
- **Lv 6-10**：可检索事实和情感记忆

#### 记忆保真度
- **新鲜（fresh）**：< 24小时，精确回忆
- **模糊（fading）**：1-7天，模糊回忆
- **遥远（distant）**：> 7天，仅核心感受

### 4. 视觉一致性系统（Visual Identity System）

确保 AI 角色在不同场景下的视觉形象一致。

#### 核心组件
- **基础肖像（base_face_url）**：角色的"身份证照片"
- **视觉标签（visual_prompt_tags）**：固定的视觉特征描述
- **面部参考（face_ref）**：图片生成时使用面部参考

#### 实现流程
1. 为角色生成基础肖像
2. 存储基础肖像 URL 到数据库
3. 生成帖子/故事时使用面部参考
4. 确保所有图片面部一致

### 5. 内容审核工作流

管理后台的内容审核系统。

#### 帖子状态
- **pending（0）**：待审核
- **published（1）**：已发布
- **rejected（2）**：已拒绝

#### 审核流程
1. AI 自动生成帖子（状态为 pending）
2. 管理员在后台审核
3. 批准后帖子公开可见
4. 拒绝后可重新生成

---

## 数据库模型

### 核心表结构

#### users（用户表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| email | String | 登录邮箱 |
| hashed_password | String | 哈希密码 |
| nickname | String | 昵称 |
| avatar_url | String | 头像 URL |
| is_admin | Integer | 管理员标识 |

#### ai_personas（AI 角色表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| name | String | 角色名称 |
| bio | String | 个人简介 |
| personality_prompt | Text | 性格设定 |
| category | String | 内容分类 |
| base_face_url | String | 基础肖像 URL |
| visual_prompt_tags | Text | 视觉标签 |

#### posts（帖子表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| ai_id | Integer | 角色 ID |
| media_url | String | 媒体 URL |
| caption | Text | 文案 |
| status | Integer | 审核状态 |

#### chat_messages（聊天消息表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| user_id | Integer | 用户 ID |
| ai_id | Integer | 角色 ID |
| role | String | 消息角色 |
| content | Text | 消息内容 |

#### emotion_states（情绪状态表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| user_id | Integer | 用户 ID |
| ai_id | Integer | 角色 ID |
| energy | Float | 能量值 |
| pleasure | Float | 愉悦度 |
| longing | Float | 思念度 |

---

## API 接口

### 认证接口

#### POST /api/auth/register
用户注册

**请求体：**
```json
{
  "email": "user@example.com",
  "password": "password123",
  "nickname": "用户昵称"
}
```

#### POST /api/auth/login
用户登录

**请求体（表单）：**
```
username=user@example.com
password=password123
```

**响应：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### 聊天接口

#### POST /api/chat/{ai_id}
发送聊天消息

**请求体：**
```json
{
  "message": "你好！",
  "post_context": null
}
```

**响应：**
```json
{
  "reply": "你好呀，今天过得怎么样？",
  "user_message_id": 123,
  "ai_message_id": 124,
  "intimacy": 0.2,
  "emotion_hint": {
    "energy_level": "normal",
    "mood": "good",
    "longing": false
  }
}
```

#### GET /api/chat/{ai_id}/history
获取聊天历史

**查询参数：**
- `limit`: 消息数量限制
- `before_id`: 游标分页

### 信息流接口

#### GET /api/feed/posts
获取帖子列表

**响应：**
```json
{
  "posts": [
    {
      "id": 1,
      "ai_id": 1,
      "media_url": "/static/posts/xxx.png",
      "caption": "今天天气真好！",
      "like_count": 42,
      "is_close_friend": false,
      "created_at": "2024-01-01T12:00:00Z"
    }
  ]
}
```

### 管理接口

#### GET /api/admin/posts/pending
获取待审核帖子

#### POST /api/admin/posts/{post_id}/approve
批准帖子

#### POST /api/admin/posts/{post_id}/reject
拒绝帖子

---

## 定时任务

### emotion_scheduler.py
**情绪调度器** - 核心 AI 行为模块

每 5 分钟扫描所有用户-角色关系，检查触发条件：

| 触发类型 | 条件 | 行为 |
|----------|------|------|
| welcome_dm | 新用户，亲密度 1-3 | 发送欢迎消息 |
| daily_checkin | 亲密度 ≥ 2，24h 未互动 | 发送日常问候 |
| memory_recall | 亲密度 ≥ 3，有相关记忆 | 引用记忆发消息 |
| longing_dm | 思念值 > 0.7，亲密度 ≥ 5 | 发送思念消息 |
| moody_story | 能量 < 30，愉悦度 < -0.3 | 发布情绪故事 |
| enthusiastic_post | 愉悦度 > 0.6，激活度 > 0.5 | 发布热情帖子 |

### post_scheduler.py
**帖子生成器**

每 6 小时执行一次：
- 为每个活跃角色生成帖子
- 根据情绪状态调整内容风格
- 消耗角色能量值

### story_cleanup.py
**故事清理器**

每小时执行一次：
- 删除过期的故事（默认 24 小时）
- 清理相关浏览记录

---

## 部署指南

### 环境要求
- Python 3.11+
- Flutter 3.x
- SQLite 3.x

### 后端部署

```bash
# 进入后端目录
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API 密钥

# 启动服务
uvicorn main:app --host 0.0.0.0 --port 8001
```

### 前端部署

```bash
# 进入前端目录
cd frontend

# 安装依赖
flutter pub get

# 构建 Web 版本
flutter build web --release

# 部署到服务器
# 将 build/web 目录部署到 Nginx
```

### 生产环境配置

```env
# .env 生产配置示例
SECRET_KEY=your-very-secure-secret-key-here
DASHSCOPE_API_KEY=sk-your-dashscope-api-key
ALLOWED_ORIGINS=https://your-domain.com
OSS_ACCESS_KEY_ID=your-oss-key-id
OSS_ACCESS_KEY_SECRET=your-oss-secret
```

---

## 开发指南

### 后端开发命令

```bash
# 启动开发服务器（热重载）
cd backend && uvicorn main:app --reload

# 运行测试
pytest tests/ -v

# 代码格式化
black . && isort .

# 类型检查
mypy . --ignore-missing-imports
```

### 前端开发命令

```bash
# 运行开发版本
cd frontend && flutter run -d chrome

# 代码分析
flutter analyze

# 代码格式化
dart format lib/
```

---

## 常见问题

### Q: 如何添加新的 AI 角色？
A: 在数据库 `ai_personas` 表中添加新记录，配置性格设定和视觉标签。

### Q: 如何修改亲密度等级边界？
A: 编辑 `aliyun_ai_service.py` 中的 `_build_boundary_constraints()` 函数。

### Q: 如何调整情绪衰减速度？
A: 编辑 `emotion_engine.py` 中的 `apply_time_decay()` 函数参数。

### Q: 如何自定义触发条件？
A: 编辑 `emotion_scheduler.py` 中的 `check_proactive_triggers()` 函数。

---

## 联系方式

如有问题，请访问 [SoulPulse 论坛](https://forum.qoder.com/) 获取支持。