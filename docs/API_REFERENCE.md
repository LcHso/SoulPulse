# SoulPulse API 参考文档

## 基础信息

**基础 URL**: `http://your-domain/api`

**认证方式**: Bearer Token (JWT)

**内容类型**: `application/json`

---

## 认证接口

### 用户注册

```
POST /api/auth/register
```

**请求体**:
```json
{
  "email": "string",        // 必填，邮箱格式
  "password": "string",     // 必填，最少 6 位
  "nickname": "string"      // 可选，默认 "User"
}
```

**响应**:
```json
{
  "id": 1,
  "email": "user@example.com",
  "nickname": "用户昵称",
  "avatar_url": null,
  "gem_balance": 100,
  "is_admin": 0,
  "created_at": "2024-01-01T00:00:00Z"
}
```

**错误码**:
- `400`: 邮箱已被注册
- `422`: 参数验证失败

---

### 用户登录

```
POST /api/auth/login
```

**请求体** (application/x-www-form-urlencoded):
```
username=user@example.com
password=password123
```

**响应**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**使用方式**:
```
Authorization: Bearer <access_token>
```

---

### 获取当前用户

```
GET /api/auth/me
```

**请求头**:
```
Authorization: Bearer <token>
```

**响应**:
```json
{
  "id": 1,
  "email": "user@example.com",
  "nickname": "用户昵称",
  "avatar_url": "https://...",
  "gem_balance": 100,
  "is_admin": 0,
  "created_at": "2024-01-01T00:00:00Z"
}
```

---

## 聊天接口

### 发送聊天消息

```
POST /api/chat/{ai_id}
```

**路径参数**:
- `ai_id`: AI 角色 ID

**请求体**:
```json
{
  "message": "你好，今天过得怎么样？",
  "post_context": null    // 可选，帖子上下文
}
```

**响应**:
```json
{
  "reply": "今天还挺充实的，刚下班回来。你呢？",
  "user_message_id": 123,
  "ai_message_id": 124,
  "intimacy": 0.4,
  "nickname_proposal": null,
  "emotion_hint": {
    "energy_level": "normal",
    "mood": "good",
    "longing": false
  }
}
```

**字段说明**:
- `reply`: AI 回复内容
- `intimacy`: 更新后的亲密度（0-10）
- `nickname_proposal`: 昵称提议（亲密度达到 6 时触发）
- `emotion_hint`: 情绪提示（用于前端 UI）

---

### 获取聊天历史

```
GET /api/chat/{ai_id}/history?limit=30&before_id=100
```

**查询参数**:
- `limit`: 消息数量，默认 30
- `before_id`: 游标分页，获取此 ID 之前的消息

**响应**:
```json
{
  "messages": [
    {
      "id": 124,
      "role": "assistant",
      "content": "今天还挺充实的...",
      "created_at": "2024-01-01T12:00:00Z"
    },
    {
      "id": 123,
      "role": "user",
      "content": "你好，今天过得怎么样？",
      "created_at": "2024-01-01T12:00:00Z"
    }
  ],
  "has_more": true
}
```

---

### 获取未送达的主动消息

```
GET /api/chat/{ai_id}/undelivered
```

**响应**:
```json
{
  "messages": [
    {
      "id": 125,
      "role": "assistant",
      "content": "好久没聊天了，最近还好吗？",
      "message_type": "proactive_dm",
      "event": "daily_checkin",
      "created_at": "2024-01-02T10:00:00Z"
    }
  ]
}
```

---

## 信息流接口

### 获取帖子列表

```
GET /api/feed/posts
```

**响应**:
```json
{
  "posts": [
    {
      "id": 1,
      "ai_id": 1,
      "ai_name": "陆晨曦",
      "ai_avatar": "https://...",
      "media_url": "/static/posts/xxx.png",
      "caption": "今天天气真好！",
      "like_count": 42,
      "is_liked": false,
      "is_saved": false,
      "is_close_friend": false,
      "created_at": "2024-01-01T12:00:00Z"
    }
  ]
}
```

**字段说明**:
- `is_liked`: 当前用户是否已点赞
- `is_saved`: 当前用户是否已收藏
- `is_close_friend`: 是否密友专属内容

---

### 点赞帖子

```
POST /api/feed/posts/{post_id}/like
```

**响应**:
```json
{
  "success": true,
  "like_count": 43
}
```

---

### 取消点赞

```
DELETE /api/feed/posts/{post_id}/like
```

---

### 收藏帖子

```
POST /api/feed/posts/{post_id}/save
```

---

### 取消收藏

```
DELETE /api/feed/posts/{post_id}/save
```

---

### 获取评论列表

```
GET /api/feed/posts/{post_id}/comments
```

**响应**:
```json
{
  "comments": [
    {
      "id": 1,
      "user_id": 1,
      "user_nickname": "小明",
      "user_avatar": "https://...",
      "content": "好漂亮的照片！",
      "is_ai_reply": false,
      "reply_to": null,
      "created_at": "2024-01-01T12:30:00Z"
    },
    {
      "id": 2,
      "ai_id": 1,
      "ai_name": "陆晨曦",
      "ai_avatar": "https://...",
      "content": "谢谢！",
      "is_ai_reply": true,
      "reply_to": 1,
      "created_at": "2024-01-01T12:31:00Z"
    }
  ]
}
```

---

### 发表评论

```
POST /api/feed/posts/{post_id}/comments
```

**请求体**:
```json
{
  "content": "好漂亮的照片！"
}
```

---

## Story 接口

### 获取故事列表

```
GET /api/feed/stories
```

**响应**:
```json
{
  "stories": [
    {
      "id": 1,
      "ai_id": 1,
      "ai_name": "陆晨曦",
      "ai_avatar": "https://...",
      "video_url": "/static/stories/xxx.mp4",
      "caption": "午后咖啡时光",
      "is_viewed": false,
      "expires_at": "2024-01-02T12:00:00Z"
    }
  ],
  "grouped_by_ai": {
    "1": [1, 2, 3]  // ai_id -> story_ids
  }
}
```

---

### 标记故事已查看

```
POST /api/feed/stories/{story_id}/view
```

---

## AI 角色接口

### 获取角色列表

```
GET /api/ai-profiles
```

**响应**:
```json
{
  "personas": [
    {
      "id": 1,
      "name": "陆晨曦",
      "bio": "温柔的外科医生",
      "profession": "医生",
      "avatar_url": "https://...",
      "category": "otome",
      "archetype": "温柔治愈",
      "intimacy": 3.5,
      "is_followed": true
    }
  ]
}
```

---

### 获取角色详情

```
GET /api/ai-profiles/{ai_id}
```

---

### 关注角色

```
POST /api/ai-profiles/{ai_id}/follow
```

---

### 取消关注

```
DELETE /api/ai-profiles/{ai_id}/follow
```

---

## 通知接口

### 获取通知列表

```
GET /api/notifications
```

**响应**:
```json
{
  "notifications": [
    {
      "id": 1,
      "type": "comment_reply",
      "title": "陆晨曦回复了你的评论",
      "body": "谢谢！",
      "data_json": "{\"ai_id\":1,\"post_id\":1}",
      "is_read": false,
      "created_at": "2024-01-01T12:31:00Z"
    }
  ],
  "unread_count": 5
}
```

---

### 标记通知已读

```
POST /api/notifications/{id}/read
```

---

### 标记全部已读

```
POST /api/notifications/read-all
```

---

## 管理接口

> 需要管理员权限（is_admin=1）

### 获取待审核帖子

```
GET /api/admin/posts/pending
```

**响应**:
```json
{
  "posts": [
    {
      "id": 1,
      "ai_id": 1,
      "ai_name": "陆晨曦",
      "media_url": "/static/posts/xxx.png",
      "caption": "待审核内容",
      "status": 0,
      "created_at": "2024-01-01T12:00:00Z"
    }
  ],
  "total": 10
}
```

---

### 批准帖子

```
POST /api/admin/posts/{post_id}/approve
```

---

### 拒绝帖子

```
POST /api/admin/posts/{post_id}/reject
```

---

### 重新生成图片

```
POST /api/admin/posts/{post_id}/regenerate
```

---

### 获取统计数据

```
GET /api/admin/analytics
```

**响应**:
```json
{
  "users_count": 100,
  "posts_count": 500,
  "stories_count": 50,
  "chats_count": 5000,
  "personas_count": 4
}
```

---

## WebSocket 接口

### 连接

```
ws://your-domain/api/chat/ws/{ai_id}?token=<jwt_token>
```

### 消息格式

**发送消息**:
```json
{
  "type": "chat",
  "content": "你好！"
}
```

**接收消息**:
```json
{
  "type": "reply",
  "content": "你好呀！",
  "message_id": 124,
  "intimacy": 0.5,
  "emotion_hint": {
    "energy_level": "normal",
    "mood": "good",
    "longing": false
  }
}
```

**主动消息**:
```json
{
  "type": "proactive_dm",
  "content": "好久不见，最近怎么样？",
  "event": "daily_checkin"
}
```

**心跳**:
```json
{
  "type": "ping"
}
```

**心跳响应**:
```json
{
  "type": "pong"
}
```

---

## 错误响应格式

所有错误响应遵循统一格式：

```json
{
  "detail": "错误描述信息"
}
```

### 常见错误码

| 状态码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未认证或 Token 过期 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 422 | 参数验证失败 |
| 500 | 服务器内部错误 |