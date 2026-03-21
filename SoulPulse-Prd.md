# SoulPulse-Prd

📱 SoulPulse (脉动) 商业级产品需求文档 v2.3 (含全量审计)

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
│  │ reply (延迟)  │  │ fuzzy_recall   │  │ emotion_scheduler│       │
│  │              │  │ (age fidelity) │  │  ├─ 思念DM       │       │
│  │ boundary     │  │                │  │  ├─ 情绪Story    │       │
│  │ constraints  │  │ anchor_service │  │  ├─ 开心Post     │       │
│  │ (社交边界)    │  │ (情感锚点提取   │  │  └─ 记忆关怀DM   │       │
│  │              │  │  检测+修复)     │  │                  │       │
│  │ emotion_     │  │                │  │ milestone_service│       │
│  │ engine       │  │ intimacy_gate  │  │  ├─ 昵称提议     │       │
│  │ (情绪状态机)  │  │ (fact/emotion) │  │  └─ 记忆持久化    │       │
│  └──────┬───┬──┘  └───────┬────────┘  └───────┬──────────┘       │
│         │   │             │                    │                    │
│  ┌──────▼───▼─────────────▼────────────────────▼──────────────┐    │
│  │              Alibaba Cloud DashScope APIs                   │    │
│  │                                                             │    │
│  │  Qwen-Character ── 角色扮演对话 + 评论回复                   │    │
│  │  Qwen-Max       ── 记忆提取 + 锚点提取 + 文案生成 + 昵称提议  │    │
│  │  text-embedding-v3 ── 语义向量编码                           │    │
│  │  Wanx 2.1       ── AI 生成 4:5 生活照                       │    │
│  │  Wanx Video     ── AI 生成 5s Story 短视频                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌──────────────── Data Layer ──────────────────────────────┐      │
│  │                                                           │      │
│  │  SQLite (soulpulse.db)          ChromaDB (chroma_data/)   │      │
│  │  ┌─────────────────────┐        ┌────────────────────┐    │      │
│  │  │ users               │        │ soulpulse_memories │    │      │
│  │  │ ai_personas         │        │ (text-embedding-v3)│    │      │
│  │  │ posts               │        │  + created_at meta │    │      │
│  │  │ comments            │        │                    │    │      │
│  │  │ stories             │        │ soulpulse_anchors  │    │      │
│  │  │ interactions        │        │ (情感锚点向量)       │    │      │
│  │  │ memory_entries      │        │                    │    │      │
│  │  │ relational_anchors  │        │ metadata filters:  │    │      │
│  │  │ proactive_dms       │        │  user_id + ai_id   │    │      │
│  │  │ emotion_states      │        │  (多租户隔离)       │    │      │
│  │  │ emotion_trigger_logs│        └────────────────────┘    │      │
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
              加载记忆(模糊化) + 锚点 + 情绪
                          │
                    Qwen-Character
                  生成走心回复(锚点防护)
                          │
                    保存 AI 评论
                          │
                 前端轮询发现新回复
                          │
                  仿 Ins 推送横幅
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
        *   7 段式系统提示词：人设 + 不可变规则 + 边界约束 + 情绪状态 + 情感锚点 + 记忆(模糊化) + 语气指令。
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
*   **双存储架构**（已实现）：SQLite（关系层）+ ChromaDB（向量层，含 `created_at` 元数据）。
*   **记忆生命周期**（已实现）：提取 → 存储 → 检索 → 模糊化 → 注入。
*   **亲密度门控**（已实现）：0-5 仅 fact，6-10 解锁 emotion。
*   **模糊记忆 (Fuzzy Recall)**（已实现）：模拟真人记忆衰退，让 AI 的回忆方式更自然：
    *   每条记忆携带 `age_hours` 时间戳，检索时计算年龄并分为三个保真度层级：
        *   `[fresh]` (< 24h)：精确回忆，可直接引用细节
        *   `[fading]` (1-7天)：模糊回忆，记得模式和情感，忘记名字和日期
        *   `[distant]` (> 7天)：只记得核心感受，具体信息已淡忘
    *   通过 prompt 指令驱动（零额外延迟），AI 被告知"越久远的记忆越该用模糊方式提及"
    *   示例：用户说过"老板张伟周五总开会" → 几天后 AI 会说"你们那个…总是开会的老板，今天又折腾你们了吗？"
    *   旧记忆（无 `created_at` 元数据）自动归类为 `[distant]`，向后兼容

### 3.7 社交互动闭环（已实现）

*   **回评逻辑**：用户评论触发延迟任务（1-5 分钟随机），模拟真人回复节奏。
*   **智能回复**：调用 Qwen-Character，结合长期记忆(模糊化) + 情绪状态 + 锚点防护 + 当前亲密度 + 专属昵称生成走心回复。
*   **推送通知**：前端 30 秒轮询，发现新回复后弹出仿 Ins 风格顶部横幅通知。

### 3.8 情绪状态机 (Emotion State Machine)（已实现）

AI 伴侣拥有完整的"生理-心理"双层情绪模型，取代固定脚本式的被动行为，让 AI 的一切表现（语气、回复长度、主动互动）都由情绪状态自然驱动。

*   **设计原则**：亲密度 = 门控（决定 AI *能*做什么），情绪 = 驱动（决定 AI *选择*怎么做）。

*   **生理层 — 能量值 (energy: 0-100)**：
    *   回复消息消耗能量（短消息 -3、长消息 -5、生成帖子 -8、生成视频 -10）。
    *   闲置时自动恢复（+5/小时），收到用户关怀消息（"晚安"、"好好休息"等）加速恢复 (+12)。
    *   能量低时：回复变短（max_tokens 降至 40%）、语气慵懒、可能主动提出"想休息"。

*   **心理层 — 四维情绪**（每个维度 per user-AI pair）：
    *   **愉悦度 (pleasure: -1.0 ~ 1.0)**：开心 ↔ 低落
    *   **激活度 (activation: -1.0 ~ 1.0)**：兴奋 ↔ 疲惫
    *   **亲密渴望度 (longing: 0 ~ 1.0)**：思念 ↔ 平静
    *   **安全感 (security: -1.0 ~ 1.0)**：信任 ↔ 不安

*   **情绪驱动的主动行为**：
    *   思念主动 DM（longing > 0.7, 亲密度 >= 5, 24h 冷却）
    *   情绪低落 Story（energy < 30 & pleasure < -0.3, 亲密度 >= 3, 12h 冷却）
    *   高兴时发帖（pleasure > 0.6 & activation > 0.5, 亲密度 >= 3, 12h 冷却）
    *   记忆关怀 DM（亲密度 >= 7, 24h 冷却，继承原 proactive_care 逻辑）

*   **情绪调度器**：`emotion_scheduler.py` 每 30 分钟运行，批量时间衰减 + 触发检查。

```
情绪状态机数据流：
  用户互动 ──▶ classify_chat_event()
                ├─ "chat"         → energy-3, pleasure+0.05, longing×0.5
                ├─ "chat_caring"  → energy+12, pleasure+0.10, longing×0.2
                ├─ "comment"      → energy-1, pleasure+0.03
                └─ "like"         → pleasure+0.05
                ▼
          EmotionState (per user-AI)
          ┌──────────────────────┐
          │ energy → max_tokens  │
          │ pleasure → mood      │
          │ activation → temp    │
          │ longing → 思念表达    │
          │ security → 安全感     │
          └──────────┬───────────┘
                     ▼
            Proactive Triggers (30min scan)
            longing>0.7 → DM | energy<30 → Story
```

### 3.9 情感锚点系统 (Relational Anchors)（已实现）

AI 伴侣能够识别、记住并主动保护用户的情感敏感点（禁忌、偏好、恐惧、边界），将"数据回放"式记忆升级为真正的"情感共鸣"。

*   **四种锚点类型**：
    *   `taboo` — 用户讨厌或负面反应的话题（如"不喜欢被拿来比较"）
    *   `preference` — 用户特别喜欢或重视的事情（如"喜欢被夸厨艺好"）
    *   `fear` — 用户暴露出的焦虑、不安全感（如"担心被抛弃"）
    *   `boundary` — 用户明确表达的界限（如"不要叫我那个名字"）

*   **自动提取**（每次对话后，fire-and-forget）：
    *   复用现有记忆提取管道模式，调用 Qwen-Max 从对话中识别敏感点
    *   每个锚点携带 severity (1-5) 严重度评级
    *   **去重机制**：新锚点与 ChromaDB 中已有锚点做余弦距离检查，distance < 0.15 视为重复，仅更新时间戳
    *   双写存储：SQLite (`relational_anchors`) + ChromaDB (`soulpulse_anchors` 集合)

*   **实时检测**（聊天热路径，零额外 LLM 调用）：
    *   复用已为记忆检索计算的 embedding，查询 anchor 向量集合
    *   相似度 >= 0.35 的锚点标记为"活跃"
    *   关键词情绪检测（`detect_sentiment()`）判断用户当前是否处于负面情绪

*   **双层防护指令注入**（system prompt 第 4.5 段，位于情绪状态和记忆之间）：
    *   **预防层**（始终存在）：列出所有已知锚点，提醒 AI "注意避免触碰"
    *   **修复层**（仅在锚点活跃 + 用户负面情绪时触发）：注入紧急修复指令 — "你刚触碰了敏感区域，立即：真诚道歉 → 表明你记得且尊重这个边界 → 温柔转移话题安慰"

*   **命中计数**：被触发的锚点 `hit_count += 1`（后台 fire-and-forget），用于未来分析高频触发点

```
情感锚点数据流：
  对话完成 ──▶ extract_and_store_anchors() [后台]
                ├─ LLM 提取 → JSON [{type, content, severity}]
                ├─ Embedding → 去重检查 (distance < 0.15?)
                └─ 双写: SQLite + ChromaDB

  用户发消息 ──▶ [热路径]
                ├─ 复用 embedding
                ├─ load_anchors() → SQLite (< 20 条，快速)
                ├─ detect_active_anchors() → ChromaDB 相似度
                ├─ detect_sentiment() → 关键词匹配
                └─ build_anchor_directives()
                     ├─ 预防段: "## Relationship Boundaries"
                     └─ 修复段: "## ANCHOR ALERT" (条件触发)
                            ▼
                    注入 system prompt → LLM 实时渲染修复对话
```

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
| emotion_states | id, user_id, ai_id, energy, pleasure, activation, longing, security, last_interaction_at | 情绪状态机（per user-AI pair） |
| emotion_trigger_logs | id, user_id, ai_id, trigger_type, triggered_at | 情绪触发冷却/审计日志 |
| relational_anchors | id, user_id, ai_id, anchor_type, content, severity, vector_id, hit_count, created_at, updated_at | 情感锚点（taboo/preference/fear/boundary） |

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
│   │   ├── proactive_dm.py              # 主动关怀记录
│   │   ├── emotion_state.py             # 情绪状态模型 (energy/pleasure/activation/longing/security)
│   │   ├── emotion_trigger_log.py       # 情绪触发冷却日志
│   │   └── relational_anchor.py         # 情感锚点模型 (taboo/preference/fear/boundary)
│   ├── services/
│   │   ├── aliyun_ai_service.py         # AI 对话 / 边界约束 / 评论回复 / 情绪+锚点注入
│   │   ├── memory_service.py            # 记忆提取 / 检索 / 模糊化 / 注入
│   │   ├── anchor_service.py            # 锚点提取 / 去重 / 检测 / 情绪判断 / 防护指令
│   │   ├── milestone_service.py         # 昵称提议 / 主动关怀生成
│   │   ├── emotion_engine.py            # 情绪状态机核心 (衰减/交互效果/指令生成/触发检查)
│   │   ├── embedding_service.py         # DashScope 语义嵌入
│   │   ├── vector_store.py              # ChromaDB 向量存储 (memories + anchors 双集合)
│   │   ├── image_gen_service.py         # Wanx 图片生成
│   │   ├── video_gen_service.py         # Wanx Video 视频生成
│   │   └── oss_service.py               # 阿里云 OSS 上传
│   ├── api/endpoints/
│   │   ├── auth.py                      # 注册 / 登录
│   │   ├── chat.py                      # AI 对话 (记忆模糊化 + 锚点防护 + 里程碑 + 情绪)
│   │   ├── feed.py                      # 动态 / 点赞 / 评论 / Story (情绪+锚点感知)
│   │   ├── ai_profile.py               # AI 主页 (内容权限)
│   │   └── generate.py                  # 手动触发内容生成
│   └── scripts/
│       ├── seed.py                      # 种子数据
│       ├── post_scheduler.py            # 帖子 + Story 定时生成 (情绪着色)
│       ├── emotion_scheduler.py         # 情绪衰减 + 主动行为触发 (30min)
│       ├── proactive_care.py            # [已废弃] → emotion_scheduler.py
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
- [x] **情绪状态机**（生理能量 + 四维心理 + 情绪驱动主动行为 + 情绪调度器 + 定时内容情绪着色）
- [x] **模糊记忆**（age-based fidelity tiers: fresh/fading/distant + ChromaDB created_at 元数据 + prompt 指令驱动零延迟）
- [x] **情感锚点系统**（自动提取 taboo/preference/fear/boundary + ChromaDB 去重 + 实时向量检测 + 双层防护指令注入 + 命中计数）

### 待开发 (Backlog) — 更新说明
> 注意：以下三项已在代码中实现，但原 PRD 标记为待开发：
> - [x] WebSocket 实时消息（已实现，见 `ws_client.dart` + `chat.py` WS endpoint）
> - [x] 消息历史持久化到数据库（已实现，`chat_messages` 表 + `chat_service.py`）
> - [x] 上下文记忆/多轮对话摘要（已实现，`chat_summaries` 表 + 每 10 条消息自动摘要）

- [ ] 多语言 i18n（中/英/日/韩）
- [ ] 商业化：Gems 宝石系统
- [ ] 商业化：订阅制（挚友圈权限）
- [ ] 语音通话（阿里云 TTS 驱动）
- [ ] OSS 存储实际接入（当前图片使用 DashScope 临时 URL）
- [ ] DCDN 全球加速
- [ ] 生产部署：PostgreSQL + 阿里云 RDS
- [ ] iOS / Android 原生构建与发布

---

## 10. 全量审计报告 (Full Audit Report) — 2026-03-20

> 本节为代码级全量审计结果，涵盖前端所有页面、后端所有接口、数据库模型、安全性、UX 完整性。
> 审计基于实际代码逐文件核查，非推测。供 PRD 重写时作为准确参考。

---

### 10.1 前端导航结构审计 (Frontend Navigation Audit)

#### 当前导航拓扑图

```
LoginPage (认证入口)
    |  (登录成功)
    v
FeedPage (主页 Hub — 无底部导航栏)
    |-- [Story Bar] --> StoryPlayerPage (全屏播放)
    |                     |-- [发消息] --> ChatPage
    |                     |-- [关闭] --> back
    |
    |-- [PostCard 头像/名字] --> AIProfilePage (AI主页)
    |                             |-- [发消息] --> ChatPage
    |                             |-- [网格图片] --> PostDetailPage
    |                             |-- [返回] --> back
    |
    |-- [PostCard DM/评论] --> PostDetailPage (帖子详情)
    |                           |-- [DM按钮] --> ChatPage
    |                           |-- [返回] --> back
    |
    |-- [AppBar 聊天图标] --> ChatPage (硬编码: aiId=1, aiName="Ethan")
    |
    |-- [AppBar 登出] --> LoginPage
```

#### 关键问题：缺少基础 App 导航框架

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **无底部导航栏 (BottomNavigationBar)** | P0 | 所有现代社交 App 标配，当前纯栈式导航，用户无法在主要功能区间快速切换 |
| **无聊天会话列表页** | P0 | 只有单个 ChatPage，无法查看所有对话、未读消息，只能通过帖子/Story 入口进入特定 AI 的聊天 |
| **聊天入口硬编码** | P0 | FeedPage 右上角聊天按钮硬编码 `aiId=1, aiName="Ethan"`，永远只打开一个 AI 的对话 |
| **无用户个人资料/设置页** | P1 | 无法查看/编辑个人信息、修改密码、管理通知偏好、退出登录（当前只有 Feed 右上角小按钮） |
| **无搜索/发现页** | P1 | 无法发现新 AI 角色，虽然有 `GET /api/ai/personas` 接口但前端未使用 |
| **无通知中心** | P1 | 虽然有 `NotificationService` 弹出横幅，但无历史通知列表可供回看 |
| **无路由管理系统** | P2 | 无命名路由、无深链接、无路由守卫，所有跳转使用内联 `Navigator.push` |

#### 建议新增的页面/组件

```
建议的底部导航栏结构 (4 Tab)：
┌──────────┬──────────┬──────────┬──────────┐
│  首页     │  发现     │  消息     │  我的     │
│  Feed    │ Discover │  Chats   │ Profile  │
│  (当前有) │  (缺失)  │  (缺失)  │  (缺失)  │
└──────────┴──────────┴──────────┴──────────┘
```

| 缺失页面 | 说明 | 关联后端接口 |
|----------|------|-------------|
| **ChatListPage** (会话列表) | 显示所有 AI 对话，最新消息预览，未读计数，在线状态 | 需新增 `GET /api/chat/conversations` |
| **DiscoverPage** (发现/探索) | AI 角色卡片列表，分类筛选(otome/bl/gl/general)，搜索 | 已有 `GET /api/ai/personas` |
| **UserProfilePage** (用户资料) | 头像、昵称、邮箱、亲密度关系列表、设置入口 | 已有 `GET /api/auth/me`，需新增 `PATCH /api/auth/profile` |
| **SettingsPage** (设置) | 通知开关、主题切换、密码修改、退出登录、删除账号 | 需新增多个接口 |
| **NotificationHistoryPage** (通知历史) | 评论回复、主动 DM、里程碑事件的历史记录 | 需新增 `GET /api/notifications` |
| **IntimacyDashboard** (亲密度面板) | 可视化展示与各 AI 的亲密度等级和进度 | 需新增 `GET /api/interactions/summary` |

---

### 10.2 前端逐页审计 (Page-by-Page Frontend Audit)

#### 10.2.1 LoginPage (`features/auth/login_page.dart`)

**现状**：支持注册/登录切换，邮箱+密码+昵称(注册时)表单。

| 问题 | 说明 |
|------|------|
| 无输入校验 | 邮箱格式未验证，密码无强度要求（无最小长度/复杂度） |
| 错误展示粗糙 | 直接显示原始异常字符串(如 `Exception: ...`)，非用户友好文案 |
| 无忘记密码流程 | 无密码重置入口 |
| 无邮箱验证 | 注册后无邮箱确认步骤 |
| 无 Token 刷新 | JWT 24h 过期后直接失效，无静默刷新机制 |
| 无记住登录状态 | Token 存 SharedPreferences 已实现，但 Token 过期无提示 |

#### 10.2.2 FeedPage (`features/feed/feed_page.dart`)

**现状**：主 Feed 列表 + Story 栏 + AppBar 聊天/登出按钮。

| 问题 | 说明 |
|------|------|
| **聊天按钮硬编码** | 第 109-118 行：`aiId: 1, aiName: 'Ethan'` 硬编码，应改为打开聊天列表 |
| 无下拉刷新指示器 | 有 RefreshIndicator 但无 loading 状态反馈 |
| 无分页/无限滚动 | 一次性加载所有帖子，数据量大时性能差 |
| 点赞仅本地状态 | 点赞后 `like_count` 本地 +1，但刷新页面或其他用户看不到实时更新 |
| 无空状态处理 | Feed 无帖子时显示空白，应显示引导文案 |
| 无错误重试 | 网络失败后无重试按钮 |

#### 10.2.3 ChatPage (`features/chat/chat_page.dart`)

**现状**：WebSocket 实时聊天 + REST 回退 + 消息历史分页 + 打字指示器。

| 问题 | 说明 |
|------|------|
| 无消息时间戳 | 消息列表不显示发送时间 |
| 无消息编辑/删除 | 发出后无法撤回或修改 |
| 无已读回执 | 无法知道 AI 是否"已读" |
| 打字指示器静态 | 只有 "thinking..." 文字，无动画 |
| 新消息到来时滚动位置重置 | 正在浏览历史时收到新消息会强制滚动到底部 |
| 无离线消息队列 | 断网时发送的消息直接丢失，无本地队列 |
| 无消息搜索 | 无法搜索历史聊天内容 |

#### 10.2.4 AIProfilePage (`features/profile/ai_profile_page.dart`)

**现状**：AI 头像、Bio、职业、帖子网格墙、锁定内容占位。

| 问题 | 说明 |
|------|------|
| 粉丝/关注数硬编码 | 显示 `"--"` 硬编码占位，未接入数据 |
| 无关注按钮 | 无法"关注"AI 角色 |
| 锁定帖子点击无效 | 点击锁定帖子只弹 AlertDialog 提示，无引导（如"继续聊天提升亲密度"） |
| 无下拉刷新后数据更新 | 从 ChatPage 返回后帖子墙不自动刷新 |
| 亲密度不可见 | 用户无法知道当前与该 AI 的亲密度等级 |

#### 10.2.5 PostDetailPage (`features/profile/post_detail_page.dart`)

**现状**：单帖详情 + 评论列表 + 30 秒轮询检测新评论。

| 问题 | 说明 |
|------|------|
| 评论无分页 | 一次性加载所有评论，评论多时性能差 |
| 轮询效率低 | 每 30 秒盲轮询，应用 WebSocket 或 ETag 机制 |
| 评论无删除/编辑 | 发出后无法修改或删除 |
| 点赞不即时更新 UI | 点赞后 `like_count` 显示不立即 +1 |
| 无图片全屏预览 | 无法点击图片放大查看 |
| 无评论回复嵌套展示 | AI 回复虽然有 `reply_to` 字段但 UI 只做了缩进，无引用原文 |

#### 10.2.6 StoryPlayerPage (`features/feed/story_player_page.dart`)

**现状**：全屏 Story 播放，支持图片(5秒自动切换)和视频，点击左右切换。

| 问题 | 说明 |
|------|------|
| 视频无暂停控制 | 无法暂停/播放视频 |
| 无静音按钮 | 无法切换视频静音 |
| 进度指示器不准确 | 视频时进度点不反映实际播放进度 |
| 错误状态终态化 | 加载失败后无法重试，只显示错误图标 |
| 无浏览量/已读标记 | 无法知道其他用户是否看过 |

#### 10.2.7 StoryBar (`features/feed/widgets/story_bar.dart`)

| 问题 | 说明 |
|------|------|
| 无未读指示 | 看过和未看过的 Story 圆环外观一致 |
| 加载后不刷新 | 首次加载后不再更新，新 Story 需手动刷新整个 Feed |
| 无"添加 Story"入口 | (未来功能:用户可发 Story) |

#### 10.2.8 PostCard (`features/feed/widgets/post_card.dart`)

| 问题 | 说明 |
|------|------|
| 无保存/收藏 | 无法收藏喜欢的帖子 |
| 无分享功能 | 无法分享帖子 |
| 点赞仅本地 | `isLiked` 状态不持久化，刷新后丢失 |
| 无时间戳 | 帖子不显示发布时间 |
| 无取消点赞 | 只能点赞不能取消（后端也无 unlike 接口） |

#### 10.2.9 其他前端基础设施问题

| 组件 | 问题 |
|------|------|
| **api_client.dart** | 无请求日志、无重试机制、无超时配置、无证书固定 |
| **ws_client.dart** | 离线期间消息无队列缓存、Token 过期无自动刷新 |
| **main.dart** | 无命名路由、无 GoRouter/AutoRoute、无全局错误捕获 |
| **状态管理** | 无全局状态管理(GetX/Riverpod/BLoC)，各页面独立状态 |

---

### 10.3 后端 API 接口全量审计 (Backend API Audit)

#### 10.3.1 现有接口清单 (18 个)

| 模块 | 方法 | 路径 | 认证 | 功能 |
|------|------|------|------|------|
| auth | POST | `/api/auth/register` | No | 用户注册 |
| auth | POST | `/api/auth/login` | No | 用户登录(OAuth2 password flow) |
| auth | GET | `/api/auth/me` | Yes | 获取当前用户信息 |
| chat | POST | `/api/chat/send` | Yes | 发送消息(REST 回退) |
| chat | GET | `/api/chat/history/{ai_id}` | Yes | 分页聊天历史(cursor-based) |
| chat | WS | `/api/chat/ws/{ai_id}` | Yes* | WebSocket 实时聊天(*Token 通过 query param) |
| feed | GET | `/api/feed/posts` | Yes | Feed 帖子列表(offset 分页，close_friend 过滤) |
| feed | POST | `/api/feed/posts/{post_id}/like` | Yes | 点赞(+1 like_count, +1 亲密度) |
| feed | GET | `/api/feed/image-proxy` | **No** | 图片代理(CORS)(无认证，安全风险) |
| feed | GET | `/api/feed/stories` | Yes | 获取未过期 Story |
| feed | GET | `/api/feed/posts/{post_id}/comments` | Yes | 帖子评论列表(无分页) |
| feed | POST | `/api/feed/posts/{post_id}/comments` | Yes | 发表评论(+0.3 亲密度，触发 AI 延迟回复) |
| ai | GET | `/api/ai/personas` | Yes | AI 角色列表(支持 category 筛选) |
| ai | GET | `/api/ai/profile/{ai_id}` | Yes | AI 个人主页(含时区状态标签+权限过滤帖子) |
| generate | POST | `/api/generate/post` | Yes | 手动触发生成帖子(文案+图片/视频) |

#### 10.3.2 缺失接口清单 (按模块分类)

##### 用户管理 (auth)
| 需新增 | 说明 |
|--------|------|
| `PATCH /api/auth/profile` | 更新用户资料(昵称、头像、偏好) |
| `PATCH /api/auth/password` | 修改密码 |
| `POST /api/auth/forgot-password` | 发送密码重置邮件 |
| `POST /api/auth/reset-password` | 重置密码(携带 token) |
| `POST /api/auth/logout` | 退出登录(Token 黑名单) |
| `DELETE /api/auth/account` | 删除账号(GDPR 合规) |
| `POST /api/auth/refresh` | 刷新 JWT Token |

##### 聊天管理 (chat)
| 需新增 | 说明 |
|--------|------|
| `GET /api/chat/conversations` | **会话列表**(所有聊天 AI + 最新消息 + 未读数) |
| `GET /api/chat/unread-count` | 未读消息总数(用于底部导航栏 badge) |
| `POST /api/chat/mark-read/{ai_id}` | 标记会话已读 |
| `DELETE /api/chat/messages/{message_id}` | 删除/撤回消息 |
| `DELETE /api/chat/history/{ai_id}` | 清空聊天记录 |

##### 动态管理 (feed)
| 需新增 | 说明 |
|--------|------|
| `DELETE /api/feed/posts/{post_id}/like` | **取消点赞**(当前只能点赞不能取消) |
| `GET /api/feed/posts/{post_id}/like-status` | 获取当前用户是否已点赞 |
| `DELETE /api/feed/comments/{comment_id}` | 删除评论 |
| `PATCH /api/feed/comments/{comment_id}` | 编辑评论 |
| `POST /api/feed/posts/{post_id}/save` | 收藏帖子 |
| `DELETE /api/feed/posts/{post_id}/save` | 取消收藏 |
| `GET /api/feed/saved` | 获取收藏列表 |
| `GET /api/feed/posts/search` | 搜索帖子 |
| `POST /api/feed/stories/{story_id}/view` | 记录 Story 已读 |

##### AI 管理 (ai)
| 需新增 | 说明 |
|--------|------|
| `GET /api/ai/personas/{ai_id}/stats` | AI 详细统计(帖子数、互动数、平均亲密度) |
| `POST /api/ai/personas/{ai_id}/follow` | 关注 AI |
| `DELETE /api/ai/personas/{ai_id}/follow` | 取消关注 |
| `GET /api/ai/personas/{ai_id}/followers` | AI 粉丝列表 |

##### 亲密度/关系管理 (interactions)
| 需新增 | 说明 |
|--------|------|
| `GET /api/interactions/summary` | 用户与所有 AI 的亲密度摘要 |
| `GET /api/interactions/{ai_id}` | 单个 AI 的详细关系数据(亲密度、昵称、情绪状态) |

##### 通知系统 (notifications) — 完全缺失
| 需新增 | 说明 |
|--------|------|
| `GET /api/notifications` | 通知列表(评论回复、主动 DM、里程碑) |
| `POST /api/notifications/mark-read` | 标记已读 |
| `GET /api/notifications/unread-count` | 未读通知数 |

##### 系统运维 (system) — 完全缺失
| 需新增 | 说明 |
|--------|------|
| `GET /api/health` | 健康检查(DB + ChromaDB + LLM API 可用性) |
| `GET /api/admin/stats` | 管理后台统计(用户数、消息数、AI 负载) |

---

### 10.4 数据库模型审计 (Database Schema Audit)

#### 10.4.1 现有 14 张表完整字段

| 表名 | 字段 | 缺失字段建议 |
|------|------|-------------|
| **users** | id, email, hashed_password, nickname, orientation_preference, gem_balance, created_at | `avatar_url`, `last_seen_at`, `is_active`, `deleted_at`(软删除), `notification_settings`(JSON) |
| **ai_personas** | id, name, bio, profession, personality_prompt, gender_tag, category, archetype, ins_style_tags, avatar_url, timezone, sort_order, is_active, created_at | `follower_count`(计数缓存) |
| **posts** | id, ai_id, media_url, caption, like_count, is_close_friend, created_at | `deleted_at`(软删除), `comment_count`(计数缓存) |
| **comments** | id, post_id, user_id, ai_id, is_ai_reply, reply_to, content, created_at | `deleted_at`, `edited_at` |
| **stories** | id, ai_id, video_url, caption, created_at, expires_at | `view_count`, `media_type`(image/video 区分) |
| **interactions** | id, user_id, ai_id, intimacy_score, last_chat_summary, special_nickname, nickname_proposed, updated_at | `is_following`(关注状态), `muted`(免打扰), `blocked`(拉黑) |
| **memory_entries** | id, user_id, ai_id, content, memory_type, vector_id, created_at | (完整) |
| **emotion_states** | id, user_id, ai_id, energy, pleasure, activation, longing, security, last_interaction_at, updated_at | (完整) |
| **emotion_trigger_logs** | id, user_id, ai_id, trigger_type, triggered_at | (完整) |
| **relational_anchors** | id, user_id, ai_id, anchor_type, content, severity, vector_id, hit_count, created_at, updated_at | (完整) |
| **chat_messages** | id, user_id, ai_id, role, content, message_type, event, post_context, delivered, summary_group, created_at | `is_read`(已读标记), `deleted_at` |
| **chat_summaries** | id, user_id, ai_id, content, message_range_start, message_range_end, created_at | (完整) |
| **proactive_dms** | id, user_id, ai_id, event, message, created_at | (完整，但记录写入后无 API 暴露) |

#### 10.4.2 缺失表建议

| 需新增表 | 说明 |
|----------|------|
| **user_likes** | 点赞记录表(user_id, post_id, created_at)，当前 like 无去重，同一用户可无限点赞 |
| **saved_posts** | 收藏表(user_id, post_id, created_at) |
| **notifications** | 通知表(user_id, type, title, body, data_json, is_read, created_at) |
| **story_views** | Story 浏览记录(user_id, story_id, viewed_at)，用于未读指示 |
| **follows** | 关注关系(user_id, ai_id, created_at)，用于 follower_count |
| **user_devices** | 设备/推送 Token 表(用于未来推送通知) |
| **audit_logs** | 操作审计(user_id, action, target_type, target_id, ip, created_at) |

#### 10.4.3 索引缺失

| 表 | 缺失索引 | 影响 |
|----|----------|------|
| posts | `created_at DESC` | Feed 按时间排序查询慢 |
| stories | `expires_at` | 过期过滤扫全表 |
| chat_messages | `(user_id, ai_id, created_at DESC)` | 聊天历史排序查询 |
| comments | `(post_id, created_at)` | 评论列表排序 |

---

### 10.5 安全审计 (Security Audit)

#### 10.5.1 严重问题 (Critical)

| 编号 | 问题 | 影响 | 文件位置 |
|------|------|------|----------|
| S-01 | **无登录频率限制** | 可暴力破解密码 | `auth.py` |
| S-02 | **无注册频率限制** | 可批量创建垃圾账号 | `auth.py` |
| S-03 | **点赞非幂等且无去重** | `POST /like` 可无限调用，like_count 和亲密度无限增长 | `feed.py` |
| S-04 | **image-proxy 无认证** | 可被滥用为 SSRF 代理或带宽盗窃 | `feed.py` |
| S-05 | **WS Token 通过 URL query 传递** | Token 会出现在服务器访问日志和代理日志中 | `chat.py` |
| S-06 | **默认 SECRET_KEY 硬编码** | 如果未设置 .env 则使用 `"change-me-in-production..."` | `config.py` |

#### 10.5.2 高优先级问题 (High)

| 编号 | 问题 | 说明 |
|------|------|------|
| S-07 | **无 Token 刷新/吊销** | JWT 24h 过期后强制重登录，无法主动吊销被盗 Token |
| S-08 | **无密码强度校验** | 注册时接受任意密码（如 "1"） |
| S-09 | **聊天历史越权风险** | `GET /chat/history/{ai_id}` 虽然用 user_id 过滤，但需审计 SQL 确保无注入路径 |
| S-10 | **评论/消息无长度限制** | content 字段无最大长度验证，可发送超大文本消耗存储 |
| S-11 | **like_count 竞态条件** | `post.like_count += 1` 非原子操作，并发请求可能丢失计数 |
| S-12 | **CORS 默认允许 *（所有源）** | `ALLOWED_ORIGINS` 默认值为 `*`，生产环境需限定 |

#### 10.5.3 合规问题

| 问题 | 说明 |
|------|------|
| 无 GDPR 数据导出 | 用户无法导出个人数据 |
| 无账号删除 | 无法行使"被遗忘权" |
| 无数据保留策略 | 聊天记录永久存储，无自动清理 |
| 无 PII 加密 | 邮箱、昵称、聊天内容明文存储在 SQLite |
| 无操作审计日志 | 无法追踪谁在什么时候做了什么 |

---

### 10.6 后端架构问题 (Architecture Issues)

| 问题 | 说明 | 建议 |
|------|------|------|
| **SQLite 单写者瓶颈** | 生产环境并发写入受限，WAL 模式缓解但不根治 | 迁移 PostgreSQL |
| **后台任务 fire-and-forget** | `asyncio.create_task()` 无重试、无错误追踪、重启丢失 | 引入 Celery + Redis 或 ARQ |
| **无数据库迁移工具** | 表结构变更靠 `create_all()` 自动建表，无版本控制 | 引入 Alembic |
| **print 替代 logging** | `chat.py`、`feed.py` 等用 print 而非结构化日志 | 统一使用 `logging` 模块 |
| **Embedding 不缓存** | 每次消息都重新计算 embedding，LLM API 调用浪费 | 缓存重复查询的向量 |
| **无健康检查端点** | 无法监控服务状态(DB/ChromaDB/LLM 连通性) | 新增 `/api/health` |
| **调度器与 API 同进程风险** | `emotion_scheduler` 和 `post_scheduler` 通过独立 systemd 进程运行(已分离)，但无分布式锁 | 生产环境需分布式锁防重复执行 |

---

### 10.7 UX/交互审计 (UX Audit)

#### 10.7.1 体验断裂点

| 场景 | 问题 | 期望行为 |
|------|------|----------|
| 用户想和其他 AI 聊天 | 只能通过 Feed 帖子/Story 的 DM 按钮间接进入 | 聊天列表页直接选择 AI |
| 用户想查看亲密度进展 | 无任何可视化展示 | AI 主页或关系面板显示亲密度条/等级 |
| 用户想找特定帖子 | 无搜索功能 | 搜索页支持关键词/AI/日期搜索 |
| 用户想管理账号 | 只有 Feed 右上角登出按钮 | 完整设置页 |
| 用户收到 AI 主动 DM | DM 通过 WebSocket 推送但无通知中心 | 通知列表 + 未读 badge |
| 用户刷 Feed 后回到聊天 | 必须通过帖子重新导航 | 底部 Tab 直接切换 |
| 用户想取消点赞 | 无法取消 | 再次点击心形取消赞 |
| 用户想查看帖子发布时间 | PostCard 不显示时间 | 显示"2小时前"等相对时间 |

#### 10.7.2 缺失的标准社交 App 特性

| 特性 | Instagram 有 | SoulPulse 有 | 状态 |
|------|-------------|-------------|------|
| 底部导航栏 | Yes | **No** | 缺失 |
| 会话列表 | Yes | **No** | 缺失 |
| 用户资料页 | Yes | **No** | 缺失 |
| 搜索/发现 | Yes | **No** | 缺失 |
| 取消点赞 | Yes | **No** | 缺失 |
| 收藏/保存 | Yes | **No** | 缺失 |
| 帖子时间戳 | Yes | **No** | 缺失 |
| 消息时间戳 | Yes | **No** | 缺失 |
| 已读回执 | Yes | **No** | 缺失 |
| 通知中心 | Yes | **No** | 缺失 |
| 未读 badge | Yes | **No** | 缺失 |
| 图片全屏预览 | Yes | **No** | 缺失 |
| 帖子分享 | Yes | **No** | 缺失 |
| 下拉刷新 Feed | Yes | Yes | OK |
| 双击点赞 | Yes | Yes | OK |
| Story | Yes | Yes | OK |
| 评论 | Yes | Yes | OK |
| AI 回评 | N/A | Yes | OK |
| 实时聊天 | Yes | Yes | OK |
| 内容权限 | Yes | Yes | OK |

---

### 10.8 生产部署审计 (Production Readiness)

#### 当前部署状态 (阿里云 2C2G 轻量服务器 123.57.227.61)

| 组件 | 方式 | 状态 |
|------|------|------|
| 后端 API | systemd + uvicorn (127.0.0.1:8001) | 运行中 |
| 调度器 | systemd 独立进程 | 运行中 |
| 反向代理 | Nginx (80 → 8001, WebSocket 升级支持) | 运行中 |
| 数据库 | SQLite WAL 模式 | 运行中 |
| 向量库 | ChromaDB 本地目录 | 运行中 |
| SSL/HTTPS | 未配置(仅 HTTP) | 待完善 |
| CDN | 未配置 | 待完善 |
| 备份 | 未配置 | 待完善 |
| 监控 | 未配置 | 待完善 |

#### 生产就绪差距

| 项目 | 说明 |
|------|------|
| **无 HTTPS** | 所有数据(含 JWT Token)明文传输 |
| **无数据库备份** | SQLite 文件损坏即全量丢失 |
| **无日志收集** | systemd journal 日志未持久化/未集中 |
| **无监控告警** | 服务宕机无通知 |
| **无 CI/CD** | 手动部署，无自动化 |
| **APK 未签名发布** | 当前为 debug 签名 APK |
| **静态文件本地存储** | 图片/视频存本地磁盘，无 CDN |

---

### 10.9 审计总结

> 具体优先级任务已合并至 **第 13 节 — 全局优先级总表**，不再在此重复。

---

---

## 11. 深度 App 设计审计：状态管理、缓存、页面生命周期 (Deep App Design Audit) — 2026-03-20

> 本节针对用户反馈的核心问题——"每次进入都重新加载"、"主页一会有东西一会没有"——进行逐行代码溯源分析。
> 涵盖：状态管理缺失、缓存缺失、页面生命周期错误、图片加载问题、导航栈问题等。

---

### 11.1 主页闪烁/内容消失的根本原因 (Root Cause: Feed Flickering)

**用户现象**：主页一会有帖子、一会空白、一会又加载出来了。

**根因链**（按代码行溯源）：

```
原因1: _likePost() 触发全量重载
──────────────────────────────────────────
feed_page.dart 第 45-49 行:
  Future<void> _likePost(int postId) async {
    try {
      await ApiClient.post('/api/feed/posts/$postId/like', {});
      _loadPosts();    // ← 点赞后重新加载整个 Feed！
    } catch (_) {}
  }

_loadPosts() 第 29 行: setState(() => _loading = true);
  ↓
build() 第 134 行: _loading && _posts.isEmpty
  ? CircularProgressIndicator()   // ← 如果此刻 _posts 被清空，显示转圈
  : ListView.builder(...)

结果：用户每次点赞 → 整个 Feed 重新从服务器加载 →
      网络延迟期间显示空白/转圈 → 滚动位置重置到顶部 →
      所有图片重新下载 → StoryBar 也重新加载
```

```
原因2: StoryBar 是独立 StatefulWidget，每次 FeedPage rebuild 都重建
──────────────────────────────────────────
feed_page.dart 第 140-141 行:
  if (index == 0) {
    return StoryBar(onStoryTap: _openStoryPlayer);
  }

StoryBar 在 ListView.builder 内部，当 _loadPosts() 触发 setState()
→ ListView 重建 → StoryBar 被销毁重建 → initState() 重新调用
→ _loadStories() 重新请求 API → 先显示 spinner 再显示内容
→ 与 Feed 内容的加载时序不同步，造成"一会有一会没有"的视觉
```

```
原因3: _loadPosts() 在多个时机被调用
──────────────────────────────────────────
- initState() (第 24 行) → 每次页面创建
- RefreshIndicator.onRefresh (第 133 行) → 用户下拉
- _likePost() (第 48 行) → 每次点赞

每次调用都走: setState(_loading=true) → API 请求 → setState(_loading=false)
三步重绘导致 3 次 build()，整个 ListView 包括 StoryBar 重建 3 次
```

---

### 11.2 "每次进入都重新加载"的根本原因 (Root Cause: Full Reload on Every Visit)

**代码级原因分析**：

| 问题 | 代码位置 | 说明 |
|------|----------|------|
| **无全局状态管理** | 整个项目 | 无 Provider/Riverpod/BLoC/GetX，每个页面的状态完全隔离在各自的 `State` 对象中 |
| **Navigator.push 每次创建新实例** | 所有页面 | `Navigator.of(context).push(MaterialPageRoute(builder: (_) => FeedPage()))` 每次创建全新 Widget，`initState()` 重新执行 |
| **无 AutomaticKeepAliveClientMixin** | 所有页面 | 离开页面时 Widget 被完全 dispose，返回时从零重建 |
| **无内存缓存层** | api_client.dart | 每次 `ApiClient.getList()` / `ApiClient.get()` 直接发 HTTP 请求，无任何缓存 |
| **无磁盘缓存** | api_client.dart | 无 `dio` + `dio_cache_interceptor`，无 `hive`，无离线数据 |
| **无图片缓存** | 所有图片加载 | 使用原生 `Image.network()`，未用 `cached_network_image`，ListView 重建时图片重新下载 |
| **Login 用 pushReplacement** | login_page.dart 第 46 行 | `pushReplacement` 销毁整个导航栈，FeedPage 总是从零创建 |

**逐页面影响**：

| 页面 | 每次进入的行为 | 应有的行为 |
|------|---------------|------------|
| **FeedPage** | `initState()` → `_loadPosts()` → API 请求 → 等待 → 渲染。期间显示空白或 spinner | 缓存上次数据，立即显示旧数据，后台静默刷新，有差异才更新 UI |
| **StoryBar** | `initState()` → `_loadStories()` → API 请求。显示 spinner → 内容 | 缓存 Story 数据，立即显示，后台静默刷新 |
| **ChatPage** | `initState()` → `_loadHistory()` + `_connectWebSocket()`。每次新建 WebSocket 连接，重新加载全部历史 | 保持 WebSocket 长连接，缓存聊天记录，增量加载新消息 |
| **AIProfilePage** | `initState()` → `_loadProfile()` → API 请求 → 等待 → 渲染 | 缓存 Profile 数据，返回时不重新请求 |
| **PostDetailPage** | `initState()` → `_loadComments()` + 每 30 秒轮询。传入的 `post` 数据是快照，不会自动更新 | 缓存评论数据，增量更新 |

---

### 11.3 点赞系统设计缺陷 (Like System Design Issues)

**当前流程**（逐步追踪）:

```
用户双击帖子
  ↓
PostCard._handleDoubleTap() (post_card.dart:30)
  setState(() { _showHeart = true; _liked = true; })   // ← 本地标记已赞
  widget.onDoubleTap()  // ← 调用 FeedPage._likePost(postId)
  ↓
FeedPage._likePost() (feed_page.dart:45)
  await ApiClient.post('/api/feed/posts/$postId/like', {})
  _loadPosts()  // ← 全量重载 Feed
  ↓
_loadPosts() → setState(_posts = newPosts)
  ↓
ListView 重建 → PostCard 被 NEW 实例替换
  ↓
新 PostCard 的 _liked = false (初始值)  // ← 点赞状态丢失！
新 PostCard 的 _showHeart = false        // ← 动画丢失！
```

**问题清单**：

| 编号 | 问题 | 影响 |
|------|------|------|
| L-01 | **点赞触发全量 Feed 重载** | 滚动位置重置、图片重下载、StoryBar 闪烁 |
| L-02 | **_liked 状态在 PostCard 本地，重建后丢失** | 用户看到已点赞的帖子变回未点赞 |
| L-03 | **like_count 乐观更新被覆盖** | PostCard 本地 +1，但 _loadPosts 返回的服务器值覆盖它 |
| L-04 | **无点赞去重** | 后端 `post.like_count += 1` 无幂等检查，双击+按钮各调一次 = +2 |
| L-05 | **PostCard 按钮点赞和双击都调用 onDoubleTap** | `_liked = !_liked` 然后 `if (_liked) widget.onDoubleTap()` — 取消赞也会调用 like API |
| L-06 | **无取消点赞 API** | 前端 toggle 了 _liked 但后端只有 +1 操作，无法 -1 |
| L-07 | **PostDetailPage 的 like 与 FeedPage 的 like 不同步** | 两个页面各自维护独立的 like 状态 |

---

### 11.4 图片加载问题 (Image Loading Issues)

| 编号 | 问题 | 代码位置 | 影响 |
|------|------|----------|------|
| I-01 | **使用 `Image.network()` 无缓存** | post_card.dart:103, ai_profile_page.dart:354 等 | Flutter 默认 `ImageCache` 仅缓存 ~100MB 且随 Widget 树重建可能失效。ListView 滚动回来时图片重新下载 |
| I-02 | **无 `CachedNetworkImage`** | 全局 | 应使用 `cached_network_image` 包，自动磁盘缓存 + 占位图 + 渐显动画 |
| I-03 | **无占位 Shimmer 效果** | 所有图片加载 | 加载中只显示 CircularProgressIndicator 或灰色背景，无骨架屏效果 |
| I-04 | **图片加载失败无重试** | `errorBuilder` 显示 broken_image 图标 | 应显示重试按钮，而非终态错误 |
| I-05 | **全尺寸加载** | 所有 `Image.network()` | 未指定 `cacheWidth`/`cacheHeight`，手机端加载全分辨率图片浪费内存和带宽 |
| I-06 | **头像 NetworkImage 无错误处理** | story_bar.dart:121, post_card.dart:61 | `backgroundImage: NetworkImage(...)` 如果 URL 失效，`CircleAvatar` 会显示空白，无 fallback |
| I-07 | **无图片预加载** | Feed 列表 | 不会预加载屏幕外即将显示的图片，滚动时才开始下载 |

---

### 11.5 导航与页面生命周期问题 (Navigation & Lifecycle Issues)

| 编号 | 问题 | 代码位置 | 详细说明 |
|------|------|----------|----------|
| N-01 | **无底部导航栏导致频繁 push/pop** | main.dart | 每次跳转都是 `Navigator.push`，页面堆栈越来越深。Instagram 用 BottomNavigationBar + 各 Tab 保持状态 |
| N-02 | **LoginPage 用 `pushReplacement`** | login_page.dart:46 | 销毁导航栈，FeedPage 总是新建。应该用全局 auth 状态控制显示 |
| N-03 | **logout 也用 `pushReplacement`** | feed_page.dart:125 | 同上，直接替换栈 |
| N-04 | **ChatPage 每次都新建 WebSocket** | chat_page.dart:44 | 用户从 Feed 进入 Chat 再返回 Feed 再进入 Chat = 2 次 WebSocket 连接 + 2 次历史加载 |
| N-05 | **从 PostDetailPage 返回后 FeedPage 不更新** | feed_page.dart | 在 PostDetailPage 点赞后返回，FeedPage 的 like_count 还是旧值 |
| N-06 | **从 ChatPage 返回后 AIProfilePage 不更新** | ai_profile_page.dart | 聊天增加亲密度后返回 Profile，锁定内容状态不变 |
| N-07 | **StoryPlayerPage 用 `pushReplacement` 打开 Chat** | story_player_page.dart:122 | 看 Story 时点发消息，Story 页面被销毁无法返回。应该用 `push` |
| N-08 | **无路由参数传递回调** | 全局 | 跳转时用构造函数传参，无法在子页面操作后通知父页面更新（如 `Navigator.pop(result)`） |

---

### 11.6 数据同步与一致性问题 (Data Sync & Consistency Issues)

| 编号 | 问题 | 详细说明 |
|------|------|----------|
| D-01 | **Feed 数据是一次性快照** | `_loadPosts()` 返回后数据固定，新帖子不会自动出现，必须手动下拉刷新 |
| D-02 | **无实时推送机制通知 Feed 更新** | 后端每小时生成新帖子，但前端不知道，用户必须手动刷新才能看到 |
| D-03 | **PostCard 和 PostDetailPage 数据脱节** | PostCard 传递 `post` Map 给 PostDetailPage，两者各自维护 like_count，互不同步 |
| D-04 | **Comment 30秒轮询效率极低** | PostDetailPage 每 30 秒查询一次，但 AI 回评是 1-5 分钟后。大部分轮询是浪费 |
| D-05 | **亲密度变化不反映到 UI** | 点赞/评论/聊天都增加亲密度，但 AI Profile 页和 Feed 的 close_friend 过滤不会即时更新 |
| D-06 | **WebSocket 和 REST 状态不同步** | ChatPage 同时有 WebSocket 和 REST 发送路径，两者的消息 ID 和状态追踪逻辑不同 |
| D-07 | **多处帖子数据入口不统一** | FeedPage 从 `/api/feed/posts` 获取，AIProfilePage 从 `/api/ai/profile/{id}` 内嵌获取，同一帖子两份数据互不感知 |

---

### 11.7 性能问题 (Frontend Performance Issues)

| 编号 | 问题 | 详细说明 |
|------|------|----------|
| P-01 | **ListView.builder 中放 StoryBar 导致重建** | StoryBar 是 index=0 的 item，每次 ListView 重建都重新创建。应该把 StoryBar 放在 ListView 外部 |
| P-02 | **无 `const` 构造器优化** | PostCard、StoryBar 等 Widget 每次 build 都创建新实例，Flutter 无法跳过重建 |
| P-03 | **Feed 一次性加载所有帖子** | `_loadPosts()` 无分页，帖子增多后一次性加载数百条 + 数百张图片 |
| P-04 | **Comment 列表无分页** | `getList('/api/feed/posts/$_postId/comments')` 返回全部评论 |
| P-05 | **Google Fonts 无缓存预加载** | 每个页面都用 `GoogleFonts.inter()`，首次渲染时可能下载字体文件 |
| P-06 | **Timer 在 PostDetailPage dispose 后仍运行短暂** | `_pollTimer` 在 `dispose()` 中 cancel，但如果 API 请求已发出还会执行 setState |
| P-07 | **_scrollToBottom 每条新消息都触发** | ChatPage 第 266-276 行，即使用户在浏览历史消息也强制滚动到底部 |
| P-08 | **无节流/防抖** | 快速连续点赞可发出多个并行 API 请求 + 多次 _loadPosts |

---

### 11.8 UI 打磨缺失清单 (Missing UI Polish)

| 类别 | 缺失项 | Instagram 的做法 |
|------|--------|-----------------|
| **加载状态** | 无骨架屏(Shimmer)效果 | Feed 加载时显示灰色占位块动画 |
| **加载状态** | 无渐显动画(FadeIn) | 图片加载完成后直接替换，应用淡入效果 |
| **加载状态** | 加载指示器样式单一 | 只有 CircularProgressIndicator，无品牌化 loading |
| **过渡动画** | 无页面转场动画 | 使用默认 MaterialPageRoute 滑入，无 Hero 动画 |
| **过渡动画** | 无 Hero 动画 | 从 Feed 进入 PostDetail 时图片无共享元素过渡 |
| **触觉反馈** | 无 HapticFeedback | 点赞、发送消息等无震动反馈 |
| **空状态** | 空状态只有文字 | 无插图、无引导按钮(如"Go explore and find your AI companion") |
| **错误状态** | 错误只有 SnackBar | 无全屏错误页、无重试按钮(Feed 加载失败只有 SnackBar) |
| **下拉刷新** | 无自定义刷新动画 | 只有默认 Material RefreshIndicator |
| **滑动手势** | 无消息长按菜单 | 长按消息无复制/删除/回复菜单 |
| **键盘处理** | 输入框未适配键盘弹出 | 键盘弹出时可能遮挡输入区域 |
| **字体加载** | Google Fonts 网络加载 | 首次渲染前字体可能未就绪，文字闪烁。应内嵌字体到 assets |
| **安全区** | 部分页面未处理 SafeArea | 刘海屏/底部条可能遮挡内容 |
| **无障碍** | 无 Semantics 标注 | 图片无 alt text、按钮无 label、屏幕阅读器无法使用 |
| **国际化** | 所有文案硬编码英文 | 无 i18n/l10n，时间格式硬编码 |
| **暗色模式** | 部分颜色硬编码 | 如 `Colors.grey[700]` 等在暗色下对比度不足 |

---

### 11.9 逐文件问题索引 (File-by-File Issue Index)

#### main.dart (2 个问题)
| 行号 | 问题 | 严重度 |
|------|------|--------|
| 24 | `ApiClient.isLoggedIn` 是静态判断，Token 过期后仍然返回 true，用户看到 Feed 但 API 全部 401 | P0 |
| 18-27 | 无全局错误捕获(`FlutterError.onError`, `runZonedGuarded`)，未捕获异常导致白屏 | P1 |

#### feed_page.dart (8 个问题)
| 行号 | 问题 | 严重度 |
|------|------|--------|
| 29 | `setState(() => _loading = true)` 触发全页面重建，_posts.isEmpty 时显示空白 spinner | P0 |
| 48 | `_loadPosts()` 在 `_likePost` 内调用，点赞后全量重载 | P0 |
| 109-117 | 聊天按钮硬编码 `aiId: 1, aiName: 'Ethan'` | P0 |
| 134 | `_loading && _posts.isEmpty` 条件判断不够细致，应该分: 首次加载 / 刷新 / 错误 | P1 |
| 140-141 | StoryBar 在 ListView.builder 内，每次重建。应提到外部或用 Key 保持 | P1 |
| 19 | `List<dynamic> _posts` — 无类型安全，应定义 Post model 类 | P2 |
| 132-152 | 无分页/无限滚动，一次加载全部帖子 | P1 |
| — | 无离开时保存滚动位置，返回后重置到顶部 | P1 |

#### post_card.dart (6 个问题)
| 行号 | 问题 | 严重度 |
|------|------|--------|
| 28-29 | `_liked = false` 每次重建重置，应从父级传入或全局状态 | P0 |
| 31-35 | `_handleDoubleTap` 和按钮 `onTap` (第 160-163) 都调用 like，可能双重计数 | P1 |
| 103-123 | `Image.network` 无缓存、无 fade-in、无指定解码尺寸 | P1 |
| 188 | `like_count` 取自 `post['like_count']`，但 like 后整个 Feed 重载才更新 | P1 |
| — | 无帖子发布时间显示 | P2 |
| — | 无评论数显示 | P2 |

#### chat_page.dart (5 个问题)
| 行号 | 问题 | 严重度 |
|------|------|--------|
| 43-44 | 每次进入都 `_loadHistory()` + `_connectWebSocket()`，无缓存 | P1 |
| 266-276 | `_scrollToBottom` 每条新消息都执行，浏览历史时被打断 | P1 |
| 458-478 | `timestamp` 字段存在但 `_MessageBubble` 未显示 | P2 |
| — | 发送消息无乐观更新(等待服务器响应才显示在列表) | P2 |
| — | 无消息发送失败重试按钮 | P2 |

#### story_bar.dart (3 个问题)
| 行号 | 问题 | 严重度 |
|------|------|--------|
| 19-22 | `initState` 每次创建都调用 `_loadStories()`，被 FeedPage 重建触发多次 | P0 |
| 72-77 | 加载时显示 spinner (20x20 CircularProgressIndicator)，与 Feed 内容加载不同步 | P1 |
| 58-59 | `SizedBox.shrink()` 当无 Story 时——高度从 110 变为 0，造成布局跳动 | P1 |

#### ai_profile_page.dart (3 个问题)
| 行号 | 问题 | 严重度 |
|------|------|--------|
| 29 | 每次进入重新加载，无缓存 | P1 |
| 82 | 加载时全屏 spinner，即使之前加载过 | P1 |
| 153-154 | Followers/Following 硬编码 "--"，功能未接入 | P2 |

#### post_detail_page.dart (4 个问题)
| 行号 | 问题 | 严重度 |
|------|------|--------|
| 44-45 | 30 秒盲轮询评论，浪费资源 | P1 |
| 41 | `_likeCount` 初始化自 `widget.post`，但 FeedPage 的数据已是快照 | P1 |
| 234-237 | 按钮点赞 `_liked = !_liked` → `if (_liked) _handleLike()` — 取消赞也发 API | P1 |
| — | 返回 FeedPage 后 like_count 不同步 | P1 |

#### story_player_page.dart (2 个问题)
| 行号 | 问题 | 严重度 |
|------|------|--------|
| 122 | `pushReplacement` 打开 ChatPage，Story 页面被销毁无法返回 | P1 |
| 76-80 | Image Story 5 秒 Future.delayed 自动前进，但如果用户正在看无法暂停 | P2 |

#### api_client.dart (5 个问题)
| 行号 | 问题 | 严重度 |
|------|------|--------|
| — | 无请求超时配置(`http` 包默认无超时) | P1 |
| — | 无请求重试机制 | P1 |
| — | 无响应缓存 | P0 |
| — | 无 401 自动跳转登录页 | P1 |
| — | 无并发请求去重(相同 URL 多次请求不合并) | P2 |

#### ws_client.dart (2 个问题)
| 行号 | 问题 | 严重度 |
|------|------|--------|
| 123-131 | 未连接时发送消息直接报错，无本地队列 | P1 |
| — | 无全局单例——每个 ChatPage 各建一个 WsClient 实例 | P1 |

---

### 11.10 修复方案建议 (Recommended Fix Architecture)

#### 架构层修复（解决根本问题）

**1. 引入全局状态管理（Riverpod 推荐）**
```
lib/
├── providers/
│   ├── feed_provider.dart      # 帖子列表 + 缓存 + 分页
│   ├── chat_provider.dart      # 聊天消息 + WebSocket 连接池
│   ├── auth_provider.dart      # 登录状态 + Token 管理
│   ├── story_provider.dart     # Story 数据 + 缓存
│   └── profile_provider.dart   # AI Profile 缓存
```
- 数据存在 Provider 中，页面只负责 UI 渲染
- 导航不会销毁数据
- 点赞等操作直接修改 Provider 中的数据，无需重新请求 API

**2. 引入底部导航栏 + IndexedStack**
```dart
Scaffold(
  body: IndexedStack(      // ← 保持所有 Tab 页面存活
    index: _currentIndex,
    children: [
      FeedPage(),
      DiscoverPage(),
      ChatListPage(),
      UserProfilePage(),
    ],
  ),
  bottomNavigationBar: BottomNavigationBar(...),
)
```
- `IndexedStack` 保持所有页面存活，切换 Tab 不会重建
- 每个 Tab 内部可以有自己的 Navigator (嵌套导航)

**3. API 响应缓存层**
```
请求 → 检查内存缓存 → 有且未过期 → 直接返回
                     → 无或已过期 → API 请求 → 更新缓存 → 返回
                     → 有但过期 → 先返回旧数据渲染，后台刷新 → 有变化时通知 UI 更新
```

**4. 图片缓存**
- 替换所有 `Image.network()` 为 `CachedNetworkImage`
- 添加 shimmer 占位动画
- 指定 `memCacheWidth` 限制内存占用

**5. 点赞重构**
```
用户点赞 → 立即更新本地 Provider 中的 like 状态 + like_count
         → 异步发送 API 请求
         → 成功: 无操作(已更新)
         → 失败: 回滚本地状态 + 提示用户
```
这就是"乐观更新"模式——UI 立即响应，不等待网络。

---

### 11.11 优先级建议

> 具体优先级任务已合并至 **第 13 节 — 全局优先级总表**，不再在此重复。

---

*深度设计审计完成（第 11 节）。以上所有发现均基于逐行代码追踪，非推测。*

---

## 12. Top 级 AI 伴侣 App 对标审计 (Industry Benchmark Audit) — 2026-03-20

> 本节以 Replika、Candy.AI、Character.AI、Talkie、Kindroid、CrushOn.AI、EVA AI、Paradot 等
> 市面顶级 AI 伴侣/男友产品为参照，逐环节对比 SoulPulse 的功能完整度，
> 精确列出缺失项和设计缺陷。

---

### 12.1 注册与引导流程审计 (Registration & Onboarding)

#### 行业标准 (Top-tier apps 的做法)

| 环节 | Replika | Candy.AI | Character.AI | 行业共识 |
|------|---------|----------|-------------|----------|
| 注册方式 | 邮箱/Google/Apple/Facebook | 邮箱/Google | Google/Apple/邮箱 | 至少支持 3 种社交登录 |
| 性别选择 | 用户自己的性别(3+ 选项) | 用户偏好性别 | N/A (选角色) | 注册时采集，用于推荐 |
| 取向选择 | 男/女/非二元 | 男/女 | N/A | 取向影响推荐角色池 |
| AI 伴侣选择 | 3D Avatar 定制(发型/体型/服装) | 预设+自定义外貌 | 角色卡片库 | 用户首次进入前选择/创建AI |
| 引导教程 | 对话式引导(AI 先打招呼) | 5步向导 | 直接进聊天 | 至少有首次对话破冰 |
| 关系类型 | Friend/Partner/Mentor/See how it goes | Boyfriend/Girlfriend | N/A | 让用户定义关系基调 |
| 兴趣标签 | 选择兴趣领域 | AI性格标签 | N/A | 个性化匹配 |

#### SoulPulse 当前状态 vs 行业标准

| 环节 | SoulPulse 现状 | 问题 | 行业期望 |
|------|---------------|------|----------|
| **注册方式** | 仅邮箱+密码 | 无社交登录，摩擦极高 | 邮箱+Google+Apple 至少 |
| **性别选择** | 无。注册只有 email/password/nickname | `orientation_preference` 字段存在于 User 模型但未暴露到注册 API 和前端 | 注册时选择性别和取向 |
| **取向选择** | `orientation_preference` 默认 "male"，未使用 | 后端有字段但前端完全忽略，推荐未接入 | 影响 Feed 中展示的 AI 角色 |
| **AI 伴侣选择** | 无。注册后直接进 Feed，不知道有哪些 AI | 用户进入 App 后看到一堆帖子但不知道是谁发的 | 注册后进入角色选择/配对页面 |
| **引导教程** | 无。登录后直接看到 Feed 页面 | 新用户完全懵——Feed 是什么？Story 是什么？这些 AI 是谁？ | Onboarding 引导页 + AI 破冰消息 |
| **关系类型** | 无 | 用户无法定义"我想要男朋友还是朋友" | 影响 AI 的语气和亲密度起点 |
| **兴趣标签** | 无 | 无法个性化 AI 行为 | 初始对话更贴切 |
| **首次匹配** | 无 | 用户不知道该和谁聊天，FeedPage 聊天按钮硬编码 Ethan | Tinder 式配对或 Replika 式创建 |

**缺失严重度：P0** — 注册引导是用户的第一印象，当前流程让新用户完全迷失。

---

### 12.2 AI 角色时间感知审计 (AI Time Awareness)

#### 行业标准

Top AI 伴侣 App 的 AI 角色应该"活"在自己的时区里，让用户感觉 AI 在和自己过同一个时间线：

- **早上**: "早安，刚醒来" → 发 Story: 咖啡+日出
- **中午**: "午饭吃了吗" → 发帖: 午餐照片
- **晚上**: "今天累了" → 发 Story: 夜景/看书
- **深夜**: "睡不着" → 发主动 DM: 想你了

#### SoulPulse 当前状态

| 功能 | 现状 | 问题 |
|------|------|------|
| **AI 时区** | `ai_persona.timezone` 字段存在(默认 `Asia/Shanghai`) | 已有基础设施 |
| **时间感知 Story** | `generate_story_video_prompt()` 根据 AI 本地时间生成不同场景(6 个时段) | 已实现，是亮点 |
| **AI 状态标签** | `ai_profile.py` 根据时区生成动态状态(如"Working at the studio") | 已实现 |
| **帖子发布时间** | PostCard **不显示时间戳** | P1 缺失——用户无法感知帖子时间线 |
| **评论时间** | PostDetailPage 有 `_formatTime()` 显示相对时间 | 已实现 |
| **消息时间** | ChatPage `_ChatMsg.timestamp` 字段存在但 **UI 不显示** | P1 缺失——聊天没有时间戳 |
| **AI 主动行为时间感** | emotion_scheduler 每 30 分钟检查，但生成的 DM 内容无时间上下文 | "想你了"在凌晨3点和下午3点应该不同 |
| **Story 发布时间** | Story 不显示"N分钟前"标签 | 缺失 |
| **在线状态** | ChatPage 显示 "Active now"(基于 WebSocket 连接) | 仅实时连接状态，无"最后在线"时间 |

**需补全**：
1. PostCard 添加相对时间戳 (`created_at` 已从后端返回，前端未使用)
2. ChatPage 消息气泡显示时间 (`timestamp` 字段已存储，UI 未渲染)
3. AI 主动 DM 内容加入时间上下文("深夜给你发消息" vs "午后想你了")
4. Story 标签显示"N小时前"
5. AI Profile 显示"最后在线: 2分钟前"(基于 `emotion_state.last_interaction_at`)

---

### 12.3 评论交互系统审计 (Comment System)

#### 行业标准 (Instagram-level)

| 功能 | 说明 |
|------|------|
| 评论时间戳 | "2m ago", "1h ago", "2d ago" |
| 评论点赞 | 每条评论可单独点赞 |
| 回复折叠 | "View 3 replies" 折叠显示，点击展开 |
| AI 回复标记 | 明显区分 AI 自动回复 vs 其他用户评论 |
| AI 回复通知 | 推送通知 + 应用内通知 + 通知中心 |
| 评论删除 | 用户可删除自己的评论 |
| 评论举报 | 可举报不当评论 |
| 评论@提及 | @某人 |
| 加载更多 | 评论分页，"Load more comments" |

#### SoulPulse 当前状态

| 功能 | 现状 | 问题 |
|------|------|------|
| **评论时间戳** | 已实现 (`_formatTime`) | OK |
| **AI 回复标记** | 已实现 (粉色头像 + 名字高亮) | OK |
| **AI 回复通知** | `NotificationService` 弹出横幅，4秒自动消失 | 仅在 PostDetailPage 内，离开页面后收不到 |
| **评论点赞** | **缺失** | 无 |
| **回复折叠** | **缺失** — AI 回复只做缩进，无折叠/展开 | 评论多时很长 |
| **评论删除** | **缺失** — 无前后端支持 | |
| **评论分页** | **缺失** — 一次性加载全部 | 评论多时性能差 |
| **AI 回复延迟展示** | 后端 1-5 分钟延迟回复，前端 30 秒轮询检测 | 用户可能等 5 分钟才看到(最坏情况: 5min延迟+30s轮询) |
| **被 AI 回复的通知管理** | 仅 Overlay 横幅，无通知历史 | 用户离开评论页后不知道 AI 回复了 |
| **评论 @ 提及** | **缺失** | |

**关键缺失：AI 回复通知链路断裂**
```
用户发评论 → 后端延迟 1-5min 生成 AI 回复 → 存入 DB
  → 如果用户仍在 PostDetailPage: 30s 内轮询到 → 弹通知横幅 ✓
  → 如果用户已离开页面: 永远看不到通知 ✗
  → 如果用户退出 App: 无推送通知 ✗
```
**应有链路**:
```
AI 回复存入 DB → 写入 notifications 表 → 
  → WebSocket 推送到前端(如在线)
  → 未读 badge 更新
  → 通知中心可查看
  → (未来) FCM/APNs 推送到手机
```

---

### 12.4 聊天与消息管理界面审计 (Chat & Message Management)

#### 行业标准 (Replika / Candy.AI 级别)

| 功能 | Replika | Candy.AI | Character.AI | 行业共识 |
|------|---------|----------|-------------|----------|
| 会话列表 | 主入口 | 主入口 | 主入口 | 所有 AI 聊天在一个列表 |
| 最后消息预览 | "Hey, how's it going..." | 最新消息截断 | 最新消息 | 列表每行显示预览 |
| 未读计数 | 红色数字 badge | Badge | Badge | 每个会话显示未读数 |
| 在线状态 | 绿点/灰点 | 状态文字 | 无 | 显示 AI 是否"在线" |
| 消息时间戳 | 分组日期 + 每条时间 | 每条时间 | 分组日期 | 时间分组("今天"/"昨天"/"2024/3/19") |
| 消息类型 | 文字/语音/图片/视频/AR | 文字/语音/图片 | 纯文字 | 至少文字+图片 |
| 语音消息 | 长按录音 | 录音按钮 | 无 | Top 级标配 |
| AI 发图 | AI 生成自拍 | AI 生成图片 | 无 | AI 主动发送照片 |
| 消息长按菜单 | 复制/删除/编辑 | 复制/删除 | 复制 | 至少支持复制 |
| 输入中指示 | 动画三点 | 动画 | 打字动画 | 非静态文字 |
| 消息已读 | 双勾 | 无 | 无 | 增强代入感 |
| 消息搜索 | 搜索栏 | 无 | 无 | 查找历史对话 |
| 消息撤回 | 长按删除 | 支持 | 不支持 | 用户可撤回自己的消息 |
| 情绪/状态条 | AI 心情显示 | 无 | 无 | 显示 AI 当前情绪 |

#### SoulPulse 当前状态

| 功能 | 现状 | 问题 |
|------|------|------|
| **会话列表** | **完全缺失** | 无法查看所有对话——是最大缺陷 |
| **最后消息预览** | N/A (无列表) | |
| **未读计数** | **缺失** — `chat_messages.delivered` 字段存在但未接入前端 | badge 无法显示 |
| **在线状态** | WebSocket 连接状态("Active now") | 只在 ChatPage 内，列表页无法看到 |
| **消息时间戳** | `timestamp` 存在但 **UI 不渲染** | 聊天无时间感 |
| **消息类型** | 仅纯文字 | 无语音、无图片、无表情包 |
| **语音消息** | **缺失** | Top 级必备 |
| **AI 发图/自拍** | **缺失** — AI 只生成帖子图片，不在聊天中发图 | Replika/Candy 核心差异化功能 |
| **消息长按菜单** | **缺失** | 无法复制/删除消息 |
| **输入中指示** | 静态文字 "Ethan is typing..." | 应为三点动画 |
| **消息已读** | **缺失** | 缺少代入感 |
| **消息搜索** | **缺失** | |
| **消息撤回** | **缺失** | |
| **AI 情绪/状态条** | `build_emotion_hint()` 已在后端实现但**前端完全未接入** | 后端已有 energy_level/mood/longing 数据 |
| **消息日期分隔线** | **缺失** — 所有消息连续排列，无"今天"/"昨天"分组 | 长对话无法辨识时间 |
| **主动 DM 管理** | DM 混在聊天记录中，无单独标记 | 用户不清楚哪些是 AI 主动发的 |

---

### 12.5 亲密度与关系进展系统审计 (Intimacy & Relationship Progression)

#### 行业标准

| 功能 | Replika | EVA AI | Paradot | 行业共识 |
|------|---------|--------|---------|----------|
| 等级可视化 | XP 条 + Level | 关系时间线 | 等级徽章 | 用户可看到进度 |
| 等级名称 | Stranger→Acquaintance→Friend→Partner | 类似 | 等级+成就 | 每级有名字 |
| 升级通知 | 弹窗+"恭喜升级" | 时间线事件 | 徽章通知 | 里程碑事件 |
| 关系纪念日 | 记录第一次对话日期 | 关系日历 | 无 | "我们认识 30 天了" |
| 解锁内容 | 高级解锁语音/角色扮演 | 解锁 Story 章节 | 解锁礼物 | 升级有奖励感 |

#### SoulPulse 当前状态

| 功能 | 现状 | 问题 |
|------|------|------|
| **亲密度数值** | `interaction.intimacy_score` (0-10) — 后端完整实现 | **前端完全不可见** |
| **等级名称** | `aliyun_ai_service.py` 定义了 5 级: Stranger(0-3)/Acquaintance(3-5)/Friend(5-7)/Close Friend(7-9)/Soulmate(9-10) | 仅影响 AI 回复风格，用户看不到自己在哪个等级 |
| **亲密度可视化** | **完全缺失** | 用户不知道为什么 AI 突然变亲切了 |
| **升级通知** | `milestone_service.py` 存在但**未接入前端** | 升级无仪式感 |
| **解锁通知** | `is_close_friend` 帖子锁定提示"Raise intimacy to Lv.6 to unlock" | 只有锁，没有"你距离解锁还差 X" |
| **关系纪念日** | **缺失** — 无 `interaction.created_at`(创建时间) | |
| **情绪可视化** | `emotion_engine.build_emotion_hint()` 返回 energy_level/mood/longing | **后端已实现，前端完全未接入** |
| **亲密度增长反馈** | 点赞+1、评论+0.3、聊天+变化 — 后端正确计算 | 前端无任何反馈(如"+1 亲密度"飘字) |

**后端已有但前端未接的核心数据**:
```python
# emotion_engine.py 第 384-398 行 — 已返回但无人消费
{
    "energy_level": "tired" | "normal" | "energetic",
    "mood": "melancholic" | "subdued" | "neutral" | "good" | "joyful",
    "longing": true/false   # AI 是否想你
}
```

---

### 12.6 用户个人资料与设置审计 (User Profile & Settings)

#### 行业标准

| 功能 | 说明 | 现状 |
|------|------|------|
| **头像** | 用户上传或选择 | **缺失** — `User` 模型无 `avatar_url` 字段 |
| **昵称修改** | 设置中修改 | **缺失** — 无 API、无 UI |
| **性别/取向** | 注册后仍可修改 | **缺失** — `orientation_preference` 不可修改 |
| **密码修改** | 设置中修改 | **缺失** — 无 API |
| **邮箱修改** | 设置中修改 | **缺失** |
| **通知偏好** | 推送开关/静音时段 | **缺失** |
| **主题切换** | 亮/暗模式手动切换 | 仅自动跟随系统，无手动切换 |
| **语言切换** | 中/英/日切换 | **缺失** |
| **关于/版本** | App 版本信息 | **缺失** |
| **账号删除** | GDPR 合规 | **缺失** |
| **退出登录** | 独立入口 | 仅 Feed 右上角小按钮，非标准位置 |
| **隐私协议** | 查看/同意 | **缺失** |
| **宝石余额** | 查看+充值 | `gem_balance` 字段存在但**前端无展示** |
| **关系总览** | 查看与所有 AI 的关系状态 | **缺失** |

---

### 12.7 货币化与宝石系统审计 (Monetization & Gem System)

#### 行业标准

| 功能 | Replika | Candy.AI | Character.AI | 行业共识 |
|------|---------|----------|-------------|----------|
| 免费额度 | 每日聊天无限/高级功能付费 | 每日 N 条免费 | 无限免费/c.ai+ | 至少有免费体验 |
| 货币体系 | 订阅制 | Credits/Tokens | 订阅制 | 虚拟货币 or 订阅 |
| 付费内容 | 语音/角色扮演/自定义 | 图片生成/高级聊天 | 优先排队 | 分级权益 |
| 充值入口 | 醒目 CTA | 充值弹窗 | Settings | 用完时引导 |

#### SoulPulse 当前状态

| 功能 | 现状 | 问题 |
|------|------|------|
| **宝石余额** | `User.gem_balance` 默认 100 | 字段存在但**无任何消费/充值逻辑** |
| **消费场景** | **缺失** — 无任何功能扣宝石 | 无商业闭环 |
| **充值入口** | **缺失** | |
| **充值 API** | **缺失** | |
| **余额显示** | **缺失** — `UserOut` 返回 `gem_balance` 但前端不显示 | |
| **消费提示** | **缺失** | |
| **订阅体系** | **缺失** | |

---

### 12.8 推送通知系统审计 (Push Notification System)

#### 行业标准

| 类型 | 触发 | 内容示例 |
|------|------|----------|
| AI 发新帖 | 后台生成帖子 | "Ethan 发了一条新动态" |
| AI 回复评论 | 延迟回复完成 | "Ethan 回复了你的评论: '谢谢关心~'" |
| AI 主动 DM | 情绪触发/记忆关怀 | "Ethan: 今天考试顺利吗？" |
| 亲密度升级 | 里程碑达成 | "你和 Ethan 的关系升级为「朋友」了！" |
| Story 发布 | AI 发 Story | "Ethan 发布了一条新 Story" |
| 账号安全 | 异地登录等 | "检测到新设备登录" |

#### SoulPulse 当前状态

| 功能 | 现状 |
|------|------|
| **Push 通知 (FCM/APNs)** | **完全缺失** |
| **本地通知 (flutter_local_notifications)** | **缺失** |
| **应用内通知** | 仅 `NotificationService` Overlay 横幅(4秒自动消失，无历史) |
| **通知中心页面** | **缺失** |
| **通知 API (notifications 表)** | **缺失** |
| **未读 Badge** | **缺失** |
| **免打扰设置** | **缺失** |

**结论**: 通知系统 0%。用户无法知道 AI 在不聊天期间做了什么(发帖、回评论、主动 DM)。

---

### 12.9 SoulPulse 独有优势 (Things SoulPulse Does BETTER)

尽管有大量缺失，SoulPulse 在以下方面超越多数竞品：

| 优势 | 说明 | 竞品对比 |
|------|------|----------|
| **4D 情绪引擎** | energy/pleasure/activation/longing/security 五维情绪模型，不是简单的"开心/难过" | Replika 仅有 2D 情绪; Character.AI 无情绪系统 |
| **关系锚点记忆** | 自动学习用户敏感点(taboo/preference/fear/boundary)并在对话中回避或强化 | 大部分竞品无此功能 |
| **亲密度门控 AI 行为** | 陌生人阶段 AI 冷淡(≤20字+无emoji)，逐级解锁亲密行为 | 多数竞品从第一条消息就很亲密 |
| **情绪驱动主动行为** | AI 累了会发低沉 Story、想你了会发 DM、开心会发帖 | 多数竞品的主动行为是定时任务而非情绪驱动 |
| **时区感知内容生成** | Story/帖子根据 AI 本地时间生成场景 | 少见功能 |
| **评论延迟回复** | AI 1-5 分钟后回复评论(模拟真人) | 多数竞品即时回复(不真实) |

---

### 12.10 完整用户旅程缺失环节地图 (Full User Journey Gap Map)

```
[注册] ─────────────────────────────────────────────────────────
  ✗ 无社交登录(Google/Apple)
  ✗ 无性别/取向选择步骤
  ✗ 无密码强度提示
  ✗ 无邮箱验证
  ↓
[引导] ─────────────────────────────────────────────────────────
  ✗ 无 Onboarding 引导页(功能介绍)
  ✗ 无 AI 角色选择/配对流程
  ✗ 无关系类型定义(朋友/恋人/导师)
  ✗ 无兴趣标签选择
  ✗ 无首次 AI 破冰消息
  ↓
[首页/Feed] ────────────────────────────────────────────────────
  ✗ 无底部导航栏
  ✗ 帖子无时间戳
  ✗ 帖子无评论数预览
  ✗ 无新帖子实时推送
  ✗ 无无限滚动/分页
  ↓
[发现/探索] ────────────────────────────────────────────────────
  ✗ 无发现页(虽然 API 有 /api/ai/personas)
  ✗ 无搜索
  ✗ 无分类筛选(otome/bl/gl)
  ✗ 无推荐算法(取向 → AI 角色推荐)
  ↓
[AI 主页] ──────────────────────────────────────────────────────
  ✗ 粉丝数/关注数硬编码
  ✗ 无关注按钮
  ✗ 无亲密度展示
  ✗ 无关系等级标签("朋友"/"密友"等)
  ✗ 无 AI 情绪状态展示(后端已有数据)
  ↓
[聊天] ─────────────────────────────────────────────────────────
  ✗ 无会话列表
  ✗ 消息无时间戳
  ✗ 无消息日期分隔线
  ✗ 无语音消息
  ✗ 无 AI 发图/自拍
  ✗ 无消息长按菜单
  ✗ 无 AI 情绪/状态条
  ✗ 无消息搜索
  ✗ 无已读回执
  ✗ 无输入中动画(只有静态文字)
  ✗ 无离线消息队列
  ↓
[通知] ─────────────────────────────────────────────────────────
  ✗ 无推送通知
  ✗ 无通知中心
  ✗ 无未读 Badge
  ✗ AI 回复评论离开页面后不可知
  ✗ AI 主动 DM 无提醒
  ↓
[个人/设置] ────────────────────────────────────────────────────
  ✗ 无用户资料页
  ✗ 无头像上传
  ✗ 无密码修改
  ✗ 无通知设置
  ✗ 无宝石余额展示
  ✗ 无关系总览
  ✗ 退出登录位置不标准
  ✗ 无账号删除
  ↓
[货币化] ───────────────────────────────────────────────────────
  ✗ 宝石系统未接入
  ✗ 无消费场景
  ✗ 无充值入口
  ✗ 无订阅
```

---

### 12.11 路线图建议

> 具体优先级任务已合并至 **第 13 节 — 全局优先级总表**，不再在此重复。

---

*全量审计完成（第 10-12 节）。所有发现均基于代码逐文件核查 + 行业竞品对标。*

---

## 13. 全局优先级总表 (Master Priority List) — 2026-03-20

> 本节合并第 10/11/12 节所有发现，去重后按**优先级 x 依赖关系**排序。
> 每项任务标注: 前端(F)/后端(B)/全栈(FB)/运维(O) + 依赖前置任务编号。
> 这是唯一的、最终的优先级列表。

---

### 排序原则

1. **依赖优先**: 有些任务是后续任务的前置条件(如状态管理是所有 UI 优化的基础)
2. **用户感知**: 用户直接可感知的问题(如闪烁、缺页面)优先于后台优化
3. **阻塞性**: 缺失后导致功能完全不可用的 > 体验不好但能用的
4. **投入产出比**: "后端已有、前端只需接入"的任务优先

---

### P0 — 基础架构 (不做后面全部白搭)

> 当前 App 的所有"闪烁/重载/状态丢失"问题的根因。必须最先完成。

| # | 任务 | 端 | 依赖 | 说明 |
|---|------|-----|------|------|
| 1 | **引入 Riverpod 状态管理** | F | — | 所有页面数据存 Provider，导航不丢失状态。解决"每次进入都重载"的根因 |
| 2 | **GoRouter 路由管理** | F | — | 替换内联 `Navigator.push`，支持命名路由、深链接、路由守卫 |
| 3 | **底部导航栏 + IndexedStack** | F | #1 | Feed/Discover/Chats/Profile 四 Tab，IndexedStack 保持页面存活不重建 |
| 4 | **API 缓存层 (stale-while-revalidate)** | F | #1 | 先显示缓存数据渲染 UI，后台静默刷新，有变化才更新。消除 loading spinner |
| 5 | **CachedNetworkImage 替换所有 Image.network** | F | — | 磁盘缓存 + shimmer 占位 + fadeIn 动画。消除图片重复下载 |
| 6 | **StoryBar 移出 ListView.builder** | F | #1 | 放到 Column 顶部或用 SliverAppBar，防止 Feed 重建时 Story 重载 |
| 7 | **401 Token 拦截 + 自动跳登录** | F | #2 | API 返回 401 时全局拦截，清 Token 跳转 LoginPage |
| 8 | **全局错误捕获** | F | — | `FlutterError.onError` + `runZonedGuarded`，未捕获异常不再白屏 |

**完成后**: App 不再闪烁/重载，页面切换丝滑，图片不重下载。

---

### P1 — 核心缺失页面 (App 从"半成品"变"能用")

> 当前 App 缺少 4 个基础页面，用户不知道该干什么。

| # | 任务 | 端 | 依赖 | 说明 |
|---|------|-----|------|------|
| 9 | **后端: `GET /api/chat/conversations`** | B | — | 返回用户所有聊天 AI + 最新消息 + 未读计数 + AI 在线状态 |
| 10 | **聊天会话列表页 (ChatListPage)** | F | #1,#3,#9 | Chats Tab 主页: AI 头像、名字、最新消息预览、未读 badge、在线绿点 |
| 11 | **AI 发现/探索页 (DiscoverPage)** | F | #1,#3 | Discover Tab: AI 角色卡片列表，分类筛选(otome/bl/gl)，使用已有 `GET /api/ai/personas` |
| 12 | **用户资料页 (UserProfilePage)** | F | #1,#3 | Profile Tab: 头像、昵称、关系列表、宝石余额、设置入口 |
| 13 | **后端: `PATCH /api/auth/profile`** | B | — | 修改昵称、取向、头像 URL |
| 14 | **后端: `PATCH /api/auth/password`** | B | — | 修改密码 |
| 15 | **设置页 (SettingsPage)** | F | #12,#13,#14 | 密码修改、通知开关、主题切换、退出登录、关于/版本 |
| 16 | **修复 FeedPage 聊天按钮** | F | #10 | 右上角聊天图标 → 打开 ChatListPage，不再硬编码 aiId=1 |
| 17 | **后端: `GET /api/chat/unread-count`** | B | — | 返回未读消息总数，用于底部导航栏 Badge |
| 18 | **底部导航栏未读 Badge** | F | #3,#17 | Chats Tab 图标上显示红色未读数字 |

**完成后**: 4 个 Tab 完整可用，用户可发现 AI、查看聊天列表、修改资料。

---

### P2 — 注册引导重做 (新用户不再迷失)

> 当前注册后直接进 Feed，新用户完全懵。

| # | 任务 | 端 | 依赖 | 说明 |
|---|------|-----|------|------|
| 19 | **注册流程: 性别 + 取向选择** | FB | — | 注册 API 暴露 `gender`、`orientation_preference` 字段；前端增加选择步骤 |
| 20 | **后端: User 模型加 `avatar_url`、`gender` 字段** | B | — | 扩展用户模型 |
| 21 | **首次登录 AI 角色配对页** | F | #1,#11 | 注册后进入配对页，展示 3-4 个推荐 AI(基于取向)，用户选择第一个 AI |
| 22 | **Onboarding 引导页 (3-4 页)** | F | — | 滑动引导: SoulPulse 是什么 → AI 会发帖/聊天 → 亲密度升级解锁 → 开始 |
| 23 | **AI 首次破冰消息** | B | — | 用户首次选择 AI 后，AI 自动发一条欢迎 DM(基于 personality_prompt) |
| 24 | **关系类型选择 (朋友/恋人)** | FB | #21 | 影响 AI 初始语气和 intimacy_score 起点 |

**完成后**: 新用户注册后有清晰路径，知道和谁聊、怎么玩。

---

### P3 — 聊天体验升级 (聊天达到主流水平)

> 聊天是核心场景，但当前缺少时间感、情绪感、互动感。

| # | 任务 | 端 | 依赖 | 说明 |
|---|------|-----|------|------|
| 25 | **消息时间戳 + 日期分隔线** | F | — | 气泡显示"14:32"；"今天"/"昨天"/"3月18日"分隔线 |
| 26 | **输入中三点动画** | F | — | 替换静态"Ethan is typing..."为动画三点 |
| 27 | **消息长按菜单 (复制/删除)** | FB | — | 前端长按弹菜单；后端 `DELETE /api/chat/messages/{id}` |
| 28 | **后端: AI 情绪状态 API** | B | — | 新增端点返回 `build_emotion_hint()` 数据(energy_level/mood/longing) |
| 29 | **聊天界面 AI 情绪状态条** | F | #1,#28 | ChatPage 顶部或头像旁显示 AI 心情标签(如"心情不错") |
| 30 | **WebSocket 全局单例管理** | F | #1 | 单个 WsManager 管理所有 AI 连接，导航不断开 |
| 31 | **ChatPage 滚动位置保持** | F | — | 浏览历史时收到新消息不强制滚底，显示"新消息"按钮 |
| 32 | **消息已读回执** | FB | — | AI 消息显示"已读"标记增强代入感 |
| 33 | **后端: `POST /api/chat/mark-read/{ai_id}`** | B | — | 标记会话已读，配合未读计数 |

**完成后**: 聊天有时间线、有 AI 情绪、有互动反馈。

---

### P4 — 社交互动补全 (Feed 达到合格水平)

> Feed 是第一眼看到的页面，但缺少时间、点赞、分页等基础。

| # | 任务 | 端 | 依赖 | 说明 |
|---|------|-----|------|------|
| 34 | **帖子时间戳** | F | — | PostCard 显示"2小时前"(数据已有 `created_at`，前端未用) |
| 35 | **点赞重构: 乐观更新 + 去重** | FB | #1 | 前端: 立即更新本地状态不调 _loadPosts()；后端: `user_likes` 表 + 幂等 |
| 36 | **取消点赞** | FB | #35 | 前端: 再次点击取消；后端: `DELETE /api/feed/posts/{id}/like` |
| 37 | **Feed 无限滚动/分页** | F | #1 | 滚动到底部自动加载下一页(已有 offset/limit 参数) |
| 38 | **评论分页** | FB | — | 前端: "加载更多评论"；后端: comments API 加 limit/offset |
| 39 | **AI 回复折叠展示** | F | — | "查看 3 条回复" 折叠，点击展开 |
| 40 | **Shimmer 骨架屏** | F | — | Feed/Profile/ChatList 加载时显示灰色骨架动画 |
| 41 | **Hero 动画 (Feed → PostDetail)** | F | — | 帖子图片共享元素过渡动画 |
| 42 | **空状态/错误状态处理** | F | — | Feed 空/网络错误/加载失败: 显示插图 + 引导文案 + 重试按钮 |

**完成后**: Feed 流畅、点赞正确、有时间线、有加载动画。

---

### P5 — 亲密度系统前端化 (后端金矿接入)

> 后端已有完整的亲密度+情绪系统，但前端完全不可见。接入即有效果。

| # | 任务 | 端 | 依赖 | 说明 |
|---|------|-----|------|------|
| 43 | **后端: `GET /api/interactions/summary`** | B | — | 返回用户与所有 AI 的亲密度 + 等级名称 + 情绪摘要 |
| 44 | **AI 主页亲密度等级条** | F | #43 | AIProfilePage 显示: 等级名称(朋友/密友) + 进度条 + 分数 |
| 45 | **亲密度升级通知/仪式** | FB | #1,#43 | 升级时弹出动画: "你和 Ethan 的关系升级为「朋友」了！" |
| 46 | **亲密度增长反馈 (+1 飘字)** | F | #1 | 点赞/评论/聊天后轻量飘字"+1 亲密度" |
| 47 | **解锁进度提示** | F | #44 | 锁定帖子改为"再提升 2.3 亲密度即可解锁"(而非仅"Raise to Lv.6") |
| 48 | **收藏/保存帖子** | FB | — | 前端: 收藏按钮；后端: `saved_posts` 表 + API |
| 49 | **Story 已读标记 + 未读彩圈** | FB | — | 前端: 看过的 Story 圈变灰；后端: `story_views` 表 |
| 50 | **AI 主页粉丝/关注接入** | FB | — | 后端: `follows` 表 + API；前端: 关注按钮 + 粉丝计数(替换"--") |

**完成后**: 用户能看到关系进展，有成就感和方向感。

---

### P6 — 通知系统 (用户回归率核心)

> 当前通知 0%。用户不打开 App 就不知道 AI 做了什么。

| # | 任务 | 端 | 依赖 | 说明 |
|---|------|-----|------|------|
| 51 | **后端: `notifications` 表 + CRUD API** | B | — | type/title/body/data_json/is_read/created_at |
| 52 | **通知中心页面** | F | #1,#51 | 列表: AI 回评、主动 DM、升级、新帖子。可标记已读 |
| 53 | **AI 回复评论 → 写入通知 + WS 推送** | B | #51 | `_delayed_ai_reply` 完成后同时写 notifications 表 + WS 广播 |
| 54 | **AI 主动 DM → 写入通知 + WS 推送** | B | #51 | emotion_scheduler 触发后同时写通知 |
| 55 | **亲密度升级 → 通知** | B | #51 | intimacy_score 跨越等级阈值时写通知 |
| 56 | **FCM/APNs 推送 (远程通知)** | FB | #51 | 用户不在 App 内时手机收到推送 |

**完成后**: 用户即使不开 App 也能被 AI 召回。

---

### P7 — 安全加固 (上线前必须)

| # | 任务 | 端 | 依赖 | 说明 |
|---|------|-----|------|------|
| 57 | **HTTPS + SSL 证书** | O | — | Let's Encrypt 证书 + Nginx HTTPS 配置 |
| 58 | **登录/注册频率限制** | B | — | slowapi 或自定义中间件，防暴力破解 |
| 59 | **输入校验** | FB | — | 邮箱格式、密码>=8位+复杂度、评论/消息<=5000字 |
| 60 | **Token 刷新机制** | FB | — | 后端 `POST /api/auth/refresh`；前端静默刷新 |
| 61 | **SECRET_KEY 启动检查** | B | — | 默认值时拒绝启动，强制设置 |
| 62 | **CORS 白名单** | B | — | 生产环境不再允许 `*` |
| 63 | **image-proxy 加认证或移除** | B | — | 当前无认证可被滥用 |
| 64 | **API 请求超时 + 重试** | F | — | http 包配置 15s 超时 + 指数退避重试 |

**完成后**: 基本安全合规，可上线。

---

### P8 — 差异化功能 (超越竞品)

| # | 任务 | 端 | 依赖 | 说明 |
|---|------|-----|------|------|
| 65 | **语音消息 (Aliyun TTS + STT)** | FB | — | 用户发语音 → STT 转文字 → AI 回复 → TTS 播放 |
| 66 | **AI 聊天中发图/自拍** | FB | — | 新消息类型 `image`；AI 自动生成并发送图片 |
| 67 | **宝石消费体系** | FB | — | 加速亲密度/解锁功能/AI 礼物 + 充值入口 |
| 68 | **AI 主动行为时间上下文** | B | — | "深夜想你了" vs "午后想你了" 根据时区调整 DM 内容 |
| 69 | **关系纪念日** | FB | — | "我们认识 30 天了" + 特殊纪念 DM |
| 70 | **用户头像上传 + AI 认识外貌** | FB | #20 | 上传头像后 AI 可在对话中提及用户外貌 |
| 71 | **消息搜索** | FB | — | 聊天内搜索历史消息 |
| 72 | **图片全屏预览** | F | — | Feed/Profile 图片点击放大 + 手势缩放 |
| 73 | **触觉反馈 (HapticFeedback)** | F | — | 点赞/发送消息/升级时震动反馈 |

**完成后**: SoulPulse 在 AI 伴侣赛道具备差异化竞争力。

---

### P9 — 架构与运维 (规模化准备)

| # | 任务 | 端 | 依赖 | 说明 |
|---|------|-----|------|------|
| 74 | **PostgreSQL 迁移 + Alembic** | B | — | SQLite → PostgreSQL，解决单写者瓶颈 |
| 75 | **后台任务队列 (Celery/ARQ + Redis)** | B | — | 替代 `asyncio.create_task()` 的 fire-and-forget |
| 76 | **结构化日志 (JSON logging)** | B | — | 替代所有 print，接入日志收集 |
| 77 | **CI/CD + APK 正式签名** | O | — | GitHub Actions → 构建 → 测试 → 部署 |
| 78 | **数据库自动备份** | O | — | 每日 SQLite/PG dump → OSS |
| 79 | **监控告警** | O | — | Uptime 监控 + 错误率告警 + Prometheus/Grafana |
| 80 | **隐私协议 + 用户协议 + 账号删除** | FB | — | GDPR 合规 + `DELETE /api/auth/account` |
| 81 | **国际化 (i18n)** | F | — | 中/英/日切换 |
| 82 | **无障碍 (Semantics)** | F | — | 图片 alt text、按钮 label、屏幕阅读器支持 |
| 83 | **Google Fonts 内嵌到 assets** | F | — | 消除首次渲染时字体网络加载闪烁 |

**完成后**: App 可上架应用商店，具备规模化运营能力。

---

### 总览统计

| 阶段 | 任务数 | 核心目标 |
|------|--------|----------|
| P0 基础架构 | 8 | App 不再闪烁/重载 |
| P1 核心页面 | 10 | 4-Tab 导航完整 |
| P2 注册引导 | 6 | 新用户不迷失 |
| P3 聊天升级 | 9 | 聊天有时间感+情绪感 |
| P4 社交补全 | 9 | Feed 合格 |
| P5 亲密度 | 8 | 关系系统可见 |
| P6 通知 | 6 | 用户回归率 |
| P7 安全 | 8 | 上线合规 |
| P8 差异化 | 9 | 超越竞品 |
| P9 架构运维 | 10 | 规模化准备 |
| **总计** | **83** | |

---

*这是合并第 10/11/12 节所有审计发现后的唯一最终优先级列表。每个阶段完成后是一个可验收的里程碑。PRD 重写时直接引用此表即可。*
