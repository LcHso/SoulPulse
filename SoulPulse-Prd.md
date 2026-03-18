# SoulPulse-Prd

📱 SoulPulse (脉动) 商业级产品需求文档 v2.0

## 1. 产品定位

*   核心理念： 基于 Ins 社交逻辑的 AI 伴侣平台，通过"生活化动态"打破 AI 的工具感。

*   目标群体： 全球乙女（Otome）用户及 Gay 志趣用户。

*   技术基座： 阿里云全球基础设施 + 阿里云百炼 (Model Studio) LLM。

---

## 2. 工程架构图 (Architecture Diagram)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Flutter Client (Web/iOS/Android)             │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Feed Page │  │Chat Page │  │AI Profile│  │Story     │           │
│  │ PostCard  │  │  DM 对话  │  │ 三格栅墙  │  │ Player   │           │
│  │ StoryBar  │  │          │  │ 锁定占位  │  │ 全屏视频  │           │
│  │ 评论入口   │  │          │  │          │  │ DM 入口   │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │              │                 │
│  ┌────┴──────────────┴──────────────┴──────────────┴─────┐         │
│  │           ApiClient (http + Bearer JWT)                │         │
│  │           NotificationService (仿 Ins 推送横幅)         │         │
│  └────────────────────────┬──────────────────────────────┘         │
└───────────────────────────┼─────────────────────────────────────────┘
                            │ HTTP REST
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Python 3.10)                     │
│                                                                     │
│  ┌─────────────────── API Endpoints ────────────────────────┐      │
│  │                                                           │      │
│  │  /api/auth      ── 注册 / 登录 (JWT + bcrypt)            │      │
│  │  /api/chat      ── AI 对话 (亲密度语气 + 记忆注入)        │      │
│  │  /api/feed      ── 动态流 / 点赞 / 评论 / Story          │      │
│  │  /api/ai        ── AI 个人主页 (内容权限控制)             │      │
│  │  /api/generate  ── 手动触发内容生成                       │      │
│  │                                                           │      │
│  └───────────┬───────────────┬───────────────┬──────────────┘      │
│              │               │               │                      │
│  ┌───────────▼──┐  ┌────────▼───────┐  ┌───▼──────────────┐       │
│  │ AI Services  │  │ Memory System  │  │ Content Pipeline │       │
│  │              │  │                │  │                  │       │
│  │ chat_with_ai │  │ extract_and_   │  │ post_scheduler   │       │
│  │ (Qwen-Char)  │  │ store_memories │  │  ├─ 图片帖子/1h  │       │
│  │              │  │ (Qwen-Max)     │  │  └─ Story视频/12h│       │
│  │ comment_     │  │                │  │                  │       │
│  │ reply (延迟)  │  │ get_contextual │  │ proactive_care   │       │
│  │              │  │ _memories      │  │  └─ 主动关怀/24h │       │
│  │ boundary     │  │ (vector search)│  │                  │       │
│  │ constraints  │  │                │  │ milestone_service│       │
│  │ (社交边界)    │  │ intimacy_gate  │  │  ├─ 昵称提议     │       │
│  │              │  │ (fact/emotion) │  │  └─ 记忆持久化    │       │
│  └──────┬───┬──┘  └───────┬────────┘  └───────┬──────────┘       │
│         │   │             │                    │                    │
│  ┌──────▼───▼─────────────▼────────────────────▼──────────────┐    │
│  │              Alibaba Cloud DashScope APIs                   │    │
│  │                                                             │    │
│  │  Qwen-Character ── 角色扮演对话 + 评论回复                   │    │
│  │  Qwen-Max       ── 记忆提取 + 文案生成 + 昵称提议            │    │
│  │  text-embedding-v3 ── 语义向量编码                           │    │
│  │  Wanx 2.1       ── AI 生成 4:5 生活照                       │    │
│  │  Wanx Video     ── AI 生成 5s Story 短视频                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌──────────────── Data Layer ──────────────────────────────┐      │
│  │                                                           │      │
│  │  SQLite (soulpulse.db)          ChromaDB (chroma_data/)   │      │
│  │  ┌─────────────────────┐        ┌────────────────────┐    │      │
│  │  │ users               │        │ memory vectors     │    │      │
│  │  │ ai_personas         │        │ (text-embedding-v3)│    │      │
│  │  │ posts               │        │                    │    │      │
│  │  │ comments ←NEW       │        │ metadata filters:  │    │      │
│  │  │ stories ←NEW        │        │  user_id + ai_id   │    │      │
│  │  │ interactions        │        │  (多租户隔离)       │    │      │
│  │  │ memory_entries      │        └────────────────────┘    │      │
│  │  │ proactive_dms       │                                  │      │
│  │  └─────────────────────┘                                  │      │
│  └───────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心数据流

```
用户发评论 ──POST──▶ 保存评论 + 亲密度+0.3
                         │
                    asyncio.create_task()
                         │
                    ┌─────▼──────┐
                    │ 延迟 1-5 min │
                    └─────┬──────┘
                          ▼
                  加载记忆 + 亲密度
                          │
                    Qwen-Character
                    生成走心回复
                          │
                    保存 AI 评论
                          │
                 前端轮询发现新回复
                          │
                  仿 Ins 推送横幅 🔔
                  "[AI名] 回复了你"
```

```
亲密度驱动体系：
  Lv 0-2  陌生人 ── ≤20字 / 无emoji / temp=0.55 / 禁止亲昵称谓
  Lv 3-5  熟人   ── 客气有礼 / 禁用endearments / temp=0.65
  Lv 5-7  朋友   ── 温暖随性 / 可分享故事 / 解锁emotion记忆
  Lv 6    ──────── 触发昵称提议 / 解锁close_friend内容 / emotion记忆
  Lv 7-9  密友   ── 亲密关怀 / 主动关怀DM / temp=0.85
  Lv 9-10 灵魂   ── 深度亲密 / 自由表达 / temp=0.92 / max_tokens=600
```

---

## 3. 功能需求细化 (Feature Details)

### 3.1 沉浸式 Ins Feed 流

*   动态展示： AI 男友会自动发布 4:5 比例的 **AI 生成高质感图片**，配上符合人设的文案（如：深夜健身、法式早餐）。
    *   **图片生成流程**：LLM 先根据人设+风格标签生成图片描述 Prompt → Wanx 模型生成 720x1280 竖版生活照 → 自动发布到 Feed。
    *   **图片代理**（已实现）：后端提供 `/api/feed/image-proxy` 代理接口，解决 Flutter Web 跨域加载 OSS 图片的 CORS 问题，前端通过代理 URL 加载图片并显示加载进度条。
    *   **视频生成流程**：同样由 LLM 生成场景描述 → Wanx Video 模型生成 5 秒短视频 → 用于 Story 限时动态。

*   交互逻辑：
    *   双击点赞： 触发红心动画，后端记录亲密度 +1。
    *   评论互动（已实现）： 用户评论后，AI 在 1-5 分钟随机延迟后回复。回复结合长期记忆 + 当前亲密度，遵循社交边界机制。前端轮询检测新回复，弹出仿 Ins 推送通知。
    *   私信跳转： 点击动态下的私信按钮，自动跳转聊天页并带入动态上下文。

*   Story (限时动态)（已实现）：
    *   顶部渐变圆圈头像，从 API 拉取真实数据，按 AI 分组。
    *   全屏视频播放器 + 循环播放 + 进度条 + 左右切换 + DM 入口。
    *   24 小时自动过期，调度器每 12 小时生成一条（每天 2 条）。
    *   **时区感知**：根据 AI 人设时区生成对应时段场景（深夜/早晨/白天/傍晚/夜晚）。

### 3.2 情感 DM (私聊系统)

*   **角色扮演模型**： 使用 Qwen-Character 模型，专为角色扮演场景优化：
    *   始终保持人设，绝不打破第四面墙。
    *   **社交边界感机制**（已实现）：
        *   动态 temperature (0.55 ~ 0.92) + max_tokens (64 ~ 600) 基于亲密度缩放。
        *   禁止亲昵称谓列表（13 个中英文词汇），低亲密度时注入硬约束。
        *   4 段式系统提示词：人设 + 不可变规则 + 边界约束 + 记忆 + 语气指令。
    *   自然的聊天风格：短句、口语化、适当的停顿和情绪表达。

*   **关系里程碑**（已实现）：
    *   亲密度跨越 Lv 6 时 AI 主动提出专属昵称（基于长期记忆生成）。
    *   昵称持久化到 interactions + memory_entries，后续对话自然使用。
    *   主动关怀脚本：每 24h 扫描亲密度 > 7 用户，根据记忆中的日程关键词发送关心 DM。

*   亲密度锁：
    *   等级 0-5: 称呼客气，close_friend 内容不可见。
    *   等级 6+: 解锁 close_friend 帖子 + emotion 记忆 + 昵称提议。
    *   等级 7+: 触发主动关怀 DM。

### 3.3 内容权限控制（已实现）

*   **Feed 过滤**：`is_close_friend` 帖子对亲密度 < 6.0 的用户隐藏。
*   **AI 主页锁定占位**：低亲密度用户看到锁定图标 + "Close friend" 提示。
*   **服务端内容遮蔽**：锁定帖子的 `media_url` + `caption` 返回空字符串，防止抓包泄露。

### 3.4 AI 内容自动生成管线

*   **定时任务**（已实现）：
    *   每小时自动生成一条 Ins 图片帖子（文案 + 图片）。
    *   每 12 小时自动生成一条 Story 短视频（时区感知场景 + 文案）。
*   **手动触发**：管理端 API 可手动触发生成（`POST /api/generate/post`）。
*   **生成流水线**：
    1.  LLM 生成 Ins 风格文案（Qwen-Max）
    2.  LLM 根据文案 + 人设生成图片/视频描述 Prompt（Qwen-Max）
    3.  Wanx 模型生成对应媒体资源
    4.  自动保存到数据库并推送到 Feed

### 3.5 AI 个人主页 (AI Profile Page)

*   **个人信息展示**（已实现）：头像、姓名、职业、Bio、实时状态标签（时区感知）、帖子数量。
*   **三格栅图片墙**（已实现）：3 列网格展示历史帖子，锁定帖子显示 🔒 占位。
*   **交互**：点击网格图片 → 帖子详情页（含评论系统），发消息按钮 → DM 聊天页。

### 3.6 长期记忆系统 (Memory System)

*   **多租户硬隔离架构**（已实现）：user_id 在数据库层和向量层双重过滤。
*   **双存储架构**（已实现）：SQLite（关系层）+ ChromaDB（向量层）。
*   **记忆生命周期**（已实现）：提取 → 存储 → 检索 → 注入。
*   **亲密度门控**（已实现）：0-5 仅 fact，6-10 解锁 emotion。

### 3.7 社交互动闭环（已实现）

*   **回评逻辑**：用户评论触发延迟任务（1-5 分钟随机），模拟真人回复节奏。
*   **智能回复**：调用 Qwen-Character，结合长期记忆 + 当前亲密度 + 专属昵称生成走心回复。
*   **推送通知**：前端 30 秒轮询，发现新回复后弹出仿 Ins 风格顶部横幅通知。

---

## 4. 数据库模型 (Database Schema)

| 表名 | 关键字段 | 备注 |
|---|---|---|
| users | id, email, nickname, hashed_password, orientation_preference, gem_balance | 用户基础表 |
| ai_personas | id, name, bio, profession, personality_prompt, gender_tag, ins_style_tags, avatar_url, timezone | AI 人格设定 |
| posts | id, ai_id, media_url, caption, like_count, is_close_friend, created_at | Ins 动态表 |
| comments | id, post_id, user_id, ai_id, is_ai_reply, reply_to, content, created_at | 评论表（支持 AI 回复链） |
| stories | id, ai_id, video_url, caption, created_at, expires_at | 限时动态（24h 过期） |
| interactions | id, user_id, ai_id, intimacy_score, last_chat_summary, special_nickname, nickname_proposed | 亲密度 + 里程碑状态 |
| memory_entries | id, user_id, ai_id, content, memory_type, vector_id, created_at | 长期记忆（fact/emotion） |
| proactive_dms | id, user_id, ai_id, event, message, created_at | 主动关怀 DM 记录（每日去重） |

---

## 5. 工程文件结构

```
SoulPulse/
├── backend/
│   ├── main.py                          # FastAPI 入口 + lifespan
│   ├── requirements.txt                 # Python 依赖
│   ├── .env / .env.example              # 密钥配置
│   ├── .gitignore
│   ├── core/
│   │   ├── config.py                    # Pydantic Settings
│   │   ├── database.py                  # SQLAlchemy async engine
│   │   └── security.py                  # JWT + bcrypt
│   ├── models/
│   │   ├── user.py                      # 用户模型
│   │   ├── ai_persona.py                # AI 人设模型
│   │   ├── post.py                      # 帖子模型
│   │   ├── comment.py                   # 评论模型 (含 AI 回复)
│   │   ├── story.py                     # 限时动态模型
│   │   ├── interaction.py               # 亲密度 + 昵称
│   │   ├── memory_entry.py              # 长期记忆模型
│   │   └── proactive_dm.py              # 主动关怀记录
│   ├── services/
│   │   ├── aliyun_ai_service.py         # AI 对话 / 边界约束 / 评论回复 / Story 提示词
│   │   ├── memory_service.py            # 记忆提取 / 检索 / 注入
│   │   ├── milestone_service.py         # 昵称提议 / 主动关怀生成
│   │   ├── embedding_service.py         # DashScope 语义嵌入
│   │   ├── vector_store.py              # ChromaDB 向量存储
│   │   ├── image_gen_service.py         # Wanx 图片生成
│   │   ├── video_gen_service.py         # Wanx Video 视频生成
│   │   └── oss_service.py               # 阿里云 OSS 上传
│   ├── api/endpoints/
│   │   ├── auth.py                      # 注册 / 登录
│   │   ├── chat.py                      # AI 对话 (记忆 + 里程碑)
│   │   ├── feed.py                      # 动态 / 点赞 / 评论 / Story
│   │   ├── ai_profile.py               # AI 主页 (内容权限)
│   │   └── generate.py                  # 手动触发内容生成
│   └── scripts/
│       ├── seed.py                      # 种子数据
│       ├── post_scheduler.py            # 帖子 + Story 定时生成
│       ├── proactive_care.py            # 主动关怀调度
│       └── test_memory_isolation.py     # 多租户隔离测试
│
├── frontend/
│   ├── pubspec.yaml
│   └── lib/
│       ├── main.dart                    # 应用入口
│       ├── core/
│       │   ├── api/api_client.dart      # HTTP 客户端 + JWT
│       │   ├── services/notification_service.dart  # 仿 Ins 推送横幅
│       │   └── theme/app_theme.dart     # Material 3 主题
│       └── features/
│           ├── auth/login_page.dart     # 登录页
│           ├── chat/chat_page.dart      # DM 聊天页
│           ├── feed/
│           │   ├── feed_page.dart       # Feed 主页
│           │   ├── story_player_page.dart  # Story 全屏播放器
│           │   └── widgets/
│           │       ├── post_card.dart   # 帖子卡片
│           │       ├── story_bar.dart   # Story 横滚栏
│           │       └── heart_animation.dart  # 点赞动画
│           └── profile/
│               ├── ai_profile_page.dart    # AI 个人主页
│               └── post_detail_page.dart   # 帖子详情 + 评论
│
├── docker-compose.yml                   # PostgreSQL 生产配置
└── SoulPulse-Prd.md                     # 本文档
```

---

## 6. 商业化埋点 (Revenue Gates)

*   Gems (宝石): 消耗宝石解锁 AI 发送的"私密图片"或"长语音"。
*   订阅制: 每月 9.9 刀，解锁所有 AI 男友的"挚友圈"权限。

## 7. 安全规范

*   **密钥管理**：所有 API Key 通过 `.env` 文件管理，`.env` 已加入 `.gitignore`，绝不硬编码或提交到版本控制。
*   **模板文件**：提供 `.env.example` 作为配置模板，新开发者复制后填入自己的密钥即可。
*   **内容防泄露**：锁定帖子服务端遮蔽 media_url + caption，不依赖前端隐藏。
*   **多租户隔离**：记忆系统在 DB 层 + 向量层双重 user_id 过滤，系统提示词注入隔离规则。

## 8. 技术栈版本

| 组件 | 技术 | 版本/模型 |
|---|---|---|
| 前端 | Flutter | 3.27.4 |
| 后端 | FastAPI + SQLAlchemy | Python 3.10 |
| AI 对话 | Qwen-Character | qwen2.5-role-play |
| AI 文案/提取 | Qwen-Max | qwen-max |
| AI 图片 | Wanx | wanx2.1-t2i-turbo |
| AI 视频 | Wanx Video | wanx-v1 |
| 语义嵌入 | DashScope | text-embedding-v3 |
| 关系数据库 | SQLite (开发) / PostgreSQL (生产) | — |
| 向量数据库 | ChromaDB | >=0.5.0 |
| 推送通知 | Flutter in-app overlay | 自研 NotificationService |

## 9. 开发进度 (Development Progress)

### 已完成 (Done)
- [x] 项目骨架搭建（Flutter + FastAPI + SQLite）
- [x] 用户注册/登录（JWT 认证 + bcrypt 密码哈希）
- [x] AI 角色对话（Qwen-Character + 亲密度语气）
- [x] **社交边界感机制**（动态 temperature/max_tokens + 禁止亲昵称谓 + 4 段式提示词）
- [x] Feed 动态流展示（分页加载、AI 头像、文案显示）
- [x] Feed 图片展示（4:5 比例 + 后端图片代理解决 CORS）
- [x] AI 内容自动生成管线（文案 + 图片 Prompt + Wanx 生成）
- [x] 定时发布脚本（每小时图片帖子 + 每 12 小时 Story 视频）
- [x] 手动触发生成 API (`POST /api/generate/post`)
- [x] 双击点赞（红心弹跳动画 + like_count +1 + 亲密度 +1）
- [x] 私信跳转（点击帖子 DM 按钮 → 聊天页，携带帖子上下文）
- [x] **Story 限时动态**（真实 API 数据 + 全屏视频播放器 + 24h 过期 + 时区感知）
- [x] OSS 上传服务代码（oss_service.py，待接入真实 key）
- [x] .env 安全密钥管理 + .gitignore
- [x] 亮色/暗色主题（Material Design 3 + Google Fonts Inter）
- [x] 种子数据脚本（seed.py 创建默认角色 Ethan）
- [x] AI 个人主页（Profile API + 三格栅图片墙 + 帖子详情页）
- [x] **长期记忆系统**（多租户硬隔离 + 双存储 + 语义嵌入 + 亲密度门控 + 后台异步提取）
- [x] **关系里程碑**（Lv 6 昵称提议 + 记忆持久化 + 主动关怀 DM）
- [x] **内容权限控制**（close_friend 过滤 + 服务端内容遮蔽 + 锁定占位 UI）
- [x] **社交互动闭环**（评论 + 延迟 AI 回复 + 记忆/亲密度感知 + 仿 Ins 推送通知）

### 待开发 (Backlog)
- [ ] 聊天系统升级：WebSocket 实时消息（当前为 HTTP 请求-响应）
- [ ] 聊天系统升级：消息历史持久化到数据库（当前仅内存）
- [ ] 聊天系统升级：上下文记忆（多轮对话摘要）
- [ ] 多语言 i18n（中/英/日/韩）
- [ ] 商业化：Gems 宝石系统
- [ ] 商业化：订阅制（挚友圈权限）
- [ ] 语音通话（阿里云 TTS 驱动）
- [ ] OSS 存储实际接入（当前图片使用 DashScope 临时 URL）
- [ ] DCDN 全球加速
- [ ] 生产部署：PostgreSQL + 阿里云 RDS
- [ ] iOS / Android 原生构建与发布
