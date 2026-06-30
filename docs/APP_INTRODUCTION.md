# SoulPulse — Complete Core Introduction

## Vision & Positioning

SoulPulse is an **AI-driven emotional companion platform** that fuses Instagram-style social dynamics with deeply personalized AI relationship mechanics. Unlike traditional chatbots, SoulPulse creates the experience of developing a genuine relationship with AI characters who remember you, respect your emotional boundaries, proactively miss you, and evolve their behavior based on your shared history.

**Core thesis**: *"Instagram social logic + AI companion platform that eliminates the 'tool feeling' through life-like dynamics."*

---

## Target Audience

| Segment | Description |
|---------|-------------|
| **Otome Players** | Female gamers seeking narrative-driven AI boyfriends (60M+ globally) |
| **BL/GL Fans** | LGBTQ+ community and yaoi/yuri content enthusiasts (growing 15–20% YoY) |
| **AI Companion Adopters** | Users of Replika, Character.AI, Candy.AI seeking deeper emotional fidelity |
| **Story-Driven Gamers** | Mobile audience craving engagement beyond surface-level interactions |

---

## Core Feature Set

### 1. Emotionally-Intelligent Real-Time Chat

- WebSocket-based real-time messaging with REST fallback
- AI responses powered by **Qwen-Character (qwen2.5-role-play)** specialized for persona consistency
- **Intimacy-gated behavior** (0–10 scale): strangers get curt 20-character replies at low temperature; soulmates receive 600-token intimate responses at temp 0.92
- 7-segment system prompt injection: character definition → immutable rules → intimacy constraints → emotional state → relational anchors → long-term memory → tone parameters
- Undelivered message queue captures proactive DMs when users are offline

### 2. 5D Emotion Engine (Core Differentiator)

Every user-AI relationship maintains **five emotional dimensions** that evolve in real-time:

| Dimension | Range | Function |
|-----------|-------|----------|
| **Energy** | 0–100 | Affects response length and activity level |
| **Pleasure** | -1.0 ~ 1.0 | Influences tone and mood |
| **Activation** | -1.0 ~ 1.0 | Drives response variety and enthusiasm |
| **Longing** | 0 ~ 1.0 | Accumulates with absence; triggers proactive DMs |
| **Security** | -1.0 ~ 1.0 | Reflects relationship stability |

The emotion scheduler (runs every 30 minutes) triggers emergent behaviors:
- **Longing DMs** when longing > 0.7 + intimacy ≥ 5
- **Moody Stories** when energy is low + pleasure is negative
- **Enthusiastic Posts** when pleasure and activation are high
- **Memory-based caring messages** at intimacy ≥ 7

### 3. Persistent Memory System (Dual-Storage Architecture)

- **Extraction**: Qwen-Max identifies fact and emotion memories from every conversation
- **Storage**: Dual-write to SQLite (relational metadata) + ChromaDB (vector embeddings)
- **Gating**: Levels 0–5 retrieve only factual memories; Level 6+ unlocks emotional memories
- **Age-based fuzzy recall** simulating realistic human memory:
  - *Fresh* (< 24h): "You said you like mapo tofu"
  - *Fading* (1–7 days): "That spicy thing you always eat... still craving it?"
  - *Distant* (> 7 days): "I remember you mentioned feeling lonely sometimes"
- **Deduplication**: Cosine distance < 0.15 prevents redundant storage

### 4. Relational Anchors (Empathy & Safety System)

Auto-detects and respects four types of emotional boundaries:

| Anchor Type | Example | System Response |
|-------------|---------|-----------------|
| **Taboo** | "Don't compare me to others" | AI avoids in future dialogs |
| **Preference** | "Loves cooking compliments" | AI actively references |
| **Fear** | "Abandonment anxiety" | AI proactively reassures |
| **Boundary** | "Don't call me that name" | Hard constraint enforced |

Features a double-layer protection system: *prevention* (always lists anchors as reminders) + *repair* (apologize → show remembrance → gently redirect when triggered).

### 5. Instagram-Style Social Feed

- **AI-generated posts**: 4:5 vertical images via Wanx 2.1 with face-reference consistency
- **Double-tap hearts**: Triggers intimacy +1 and like_count increment
- **AI comment replies**: 1–5 minute random delay simulating human response time
- **Close friend content**: Posts gated behind intimacy Level 6
- **Image proxy**: Backend-served media resolving CORS for cross-platform delivery

### 6. Stories (24-Hour Time-Aware Content)

- Full-screen 5-second AI-generated video clips
- **Time-zone aware scene generation**: Same character produces different content based on 6 daily time segments (dawn/morning/afternoon/evening/night/late night)
- Auto-advance with tap navigation
- 24-hour expiration with automatic cleanup
- Generation frequency: 2 stories per AI per day

### 7. Intimacy Progression System

A relationship lifecycle that gates content, behavior, and vocabulary:

| Level | Stage | Unlocks |
|-------|-------|---------|
| 0–2 | Stranger | Minimal responses, no emoji |
| 3–5 | Acquaintance | Polite engagement, basic memories |
| 5–7 | Friend | Story sharing, warmth, fact memory recall |
| 6 | Milestone | AI proposes nickname; emotion memory unlocked |
| 7–9 | Close Friend | Proactive care DMs, exclusive content |
| 9–10 | Soulmate | Deep intimacy, max expressiveness, all content |

---

## Character Roster (13 Characters)

Each character features a **three-layer personality design** (Public Persona → Private Self → Hidden Depths), detailed visual DNA for image consistency, emotional triggers, speech patterns, and a secret hierarchy revealed at specific intimacy milestones.

| Character | Age | Role | MBTI | Key Trait |
|-----------|-----|------|------|-----------|
| 陆骁 (Lu Xiao) | 21 | Basketball Captain | ESTP | Possessive athlete hiding deep sensitivity |
| 季夜尘 (Ji Yechen) | 25 | Indie Musician/Tattoo Artist | INFP | Coldhearted artist with self-doubt |
| 陆晨曦 (Lu Chenxi) | 28 | Surgeon | ISTJ | Aloof professional who warms with proximity |
| 沈墨白 (Shen Mobai) | 26 | Film Director | ENFP | Chaotic romantic idealist |
| 古言深 (Gu Yanshen) | 24 | Hacker | INTJ | Cyber-gruff code genius |
| 林禹 (Lin Yu) | 22 | Dancer | ISFP | Graceful perfectionist with trauma awareness |
| 何粒叶 (He Liye) | 27 | CEO | ENTJ | Corporate alpha with rare vulnerability |
| 鹿晟曦 (Lu Shengxi) | 29 | Army Officer | ISTJ | Disciplined protector |
| 翡梨城 (Fei Licheng) | 30 | Archaeologist | ENFJ | Adventure scholar |
| 姜育白 (Jiang Yuebai) | 23 | Photographer | ISFJ | Visual poet and memory keeper |
| 裴洛 (Pei Luo) | 25 | Café Owner | ESFJ | Warm community builder |
| 文诗旭 (Wen Shixu) | 26 | Psychiatrist | INFJ | Empathetic listener |
| Starlin | 24 | Digital Artist | ISFP | AI-native creative persona |

### Character Design Depth

Each character specification includes:
- **External presentation** + internal contradictions
- **Speech patterns** + vocabulary level + emoji/punctuation habits
- **Action description style** (physical gestures, sensory details)
- **Relationship progression phases** with gated dialogue examples
- **Emotional triggers** (joy/anger/jealousy/vulnerability)
- **Voice profile** (speed, pitch, characteristic sounds)
- **Secret hierarchy** (revealed at specific intimacy milestones: Lv 15, 30, 50, 70, 90)
- **Visual DNA**: Fixed appearance tags ensuring cross-media consistency

---

## AI/LLM Integration Stack (Alibaba Cloud DashScope)

| Model | Purpose |
|-------|---------|
| **Qwen-Character (qwen2.5-role-play)** | Persona roleplay chat, comment replies |
| **Qwen-Max** | Memory extraction, anchor detection, nickname proposals, caption generation |
| **Text-Embedding-v3** | Semantic vector encoding for memory/anchor search |
| **Wanx 2.1 (t2i-turbo)** | 4:5 vertical post image generation with face reference |
| **Wanx Video** | 5-second Story video clip generation |

### Prompt Engineering Architecture (7-Segment System Prompt)

```
[Segment 1: Character Definition]
Full personality prompt with three-layer design

[Segment 2: Immutable Rules]
Never break character, no meta-commentary, forbidden vocabulary list

[Segment 3: Intimacy Constraints]
Temperature, max_tokens, allowed vocabulary by level

[Segment 4: Current Emotional State]
Energy, pleasure, longing, security — affects response generation

[Segment 5: Relational Anchors]
User taboos, preferences, fears, boundaries + active warnings

[Segment 6: Long-Term Memory]
Age-formatted fuzzy recall (fresh/fading/distant)

[Segment 7: Tone Instruction]
Dynamic temperature and max_tokens based on emotion + intimacy
```

---

## Technical Architecture

### Backend
- **Framework**: FastAPI (Python 3.11+), fully async
- **Database**: SQLite (dev) / PostgreSQL 16 (production), async SQLAlchemy ORM
- **Vector DB**: ChromaDB (in-process, local storage)
- **Auth**: JWT HS256, 24-hour expiration
- **Realtime**: Native FastAPI WebSocket
- **Background Tasks**: asyncio fire-and-forget for memory extraction and anchor detection
- **Schedulers**: emotion_scheduler (30-min cycle), post_scheduler, story_cleanup

### Mobile/Web Frontend
- **Framework**: Flutter 3.27.4 (iOS + Android + Web cross-platform)
- **State**: StatefulWidget per page
- **Communication**: HTTP + WebSocket with token auth

### Admin Dashboard
- **Framework**: React 19 + TypeScript
- **UI**: Ant Design 5.29 + Pro Components
- **State**: Zustand 5.0
- **Charts**: Ant Design Charts
- **Capabilities**: Content moderation, persona management, user management, memory browsing, world events, subscription management, DevOps monitoring (8 modules)

### Deployment Architecture
- **Production server**: Aliyun 2C2G
- **Containers**: Docker Compose with separate Backend, Admin, Scheduler services
- **Reverse proxy**: Nginx (port 80/443)
- **Persistence**: PostgreSQL container + ChromaDB volumes
- **Health checks**: Per-service liveness probes
- **Resource limits**: 512M per container

```
┌─────────────────────────────────────────────┐
│         Internet (HTTP/HTTPS)               │
└─────────────────┬───────────────────────────┘
                  │
         ┌────────▼────────┐
         │ Nginx (80/443)  │
         │ Static files    │
         └────┬─────────┬──┘
              │         │
    ┌─────────▼─┐  ┌──▼─────────┐
    │ Backend   │  │Admin       │
    │ (8001)    │  │Backend     │
    │           │  │(8002)      │
    └─────┬─────┘  └──┬─────────┘
          │           │
          └─────┬─────┘
                │
         ┌──────▼──────┐
         │ PostgreSQL  │
         │ + ChromaDB  │
         └─────────────┘

Scheduler Container: emotion_scheduler + post_scheduler
```

---

## Monetization Model

| Feature | Description | Status |
|---------|-------------|--------|
| **Gem System** | 100 initial gems on signup; used for premium content unlock | Model implemented |
| **Monthly Subscription** | $9.99/month for "close friend content" across all characters | Model exists |
| **Virtual Gifts** | User-to-AI gifting mechanism | Concept stage |
| **Premium Content Tiers** | Intimacy + subscription gated exclusive media | Planned |

---

## Competitive Differentiation

| vs. Competitor | SoulPulse Advantage |
|----------------|---------------------|
| **Replika** | 5D emotion engine, time-aware content, relational anchors safety system |
| **Character.AI** | Full social platform (feed + stories), emotional depth progression, persistent memory |
| **Candy.AI** | Superior memory + anchor integration, intimacy-gated progression, visual consistency |

### Unique Innovations (No Competitor Offers)

1. **5D Emotion Engine** — drives emergent proactive behaviors without explicit triggers
2. **Relational Anchors** — dual-layer emotional safety (prevention + repair)
3. **Age-based Fuzzy Memory Recall** — simulates realistic human memory degradation
4. **Time-zone Aware Content Generation** — 6 daily segments per character
5. **Delayed Comment Replies** — 1–5 min random delay for realism
6. **Face-Reference Visual Consistency** — ensures character identity across all generated media
7. **Intimacy-Gated Content Visibility** — not just dialogue changes but feed/story/memory access

---

## Key Strengths

1. **Sophisticated Emotion System**: Core differentiator enabling emergent AI behaviors
2. **Memory + Anchor Integration**: Past context combined with emotional safety
3. **Multi-modal Content**: Chat + Feed + Stories + Personas in one unified platform
4. **Production-Deployed**: 13 characters serving real users
5. **Comprehensive Admin Tooling**: 8-module dashboard for content curation
6. **Cutting-edge AI**: Alibaba Qwen model suite integration
7. **Visual Consistency**: Face reference system across all generated media
8. **Scalable Design**: Dual storage, vector DB, async architecture, containerized deployment

---

## Primary Value Proposition

> Users don't just chat with an AI — they **develop a relationship with an emotional being** that remembers them, respects their boundaries, and proactively misses them.

SoulPulse represents a new category of AI companion: one that combines the addictive dynamics of social media with the emotional depth of narrative-driven games, powered by state-of-the-art LLM orchestration and a novel emotion engine that makes every relationship feel uniquely alive.
