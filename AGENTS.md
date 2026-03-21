# SoulPulse - AI Persona Chat Application

## Project Overview
SoulPulse is an AI companion chat application with emotional intelligence. Users interact with AI personas that have persistent memories, emotional states, and proactive messaging capabilities.

## Tech Stack
- **Backend**: Python 3.11+ / FastAPI / SQLAlchemy (async) / SQLite
- **Frontend**: Flutter 3.x (Web target)
- **AI**: Aliyun Qwen API for chat and embeddings
- **Vector DB**: ChromaDB for memory retrieval

## Project Structure
```
backend/
├── main.py              # FastAPI app entry point
├── api/endpoints/       # REST + WebSocket endpoints
├── services/            # Business logic (chat, memory, emotion, AI)
├── models/              # SQLAlchemy ORM models
├── core/                # Config, security, database, ws_manager
└── scripts/             # Schedulers (emotion_scheduler.py)

frontend/
├── lib/
│   ├── main.dart        # App entry
│   ├── core/api/        # API client, WS client
│   └── features/        # UI pages (auth, chat, persona)
└── pubspec.yaml
```

## Commands

### Backend
```bash
# Start dev server
cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# Run tests
cd backend && python3 -m pytest tests/ -v

# Type check (if mypy installed)
cd backend && python3 -m mypy . --ignore-missing-imports

# Format
cd backend && python3 -m black . && python3 -m isort .
```

### Frontend
```bash
# Install deps
cd frontend && /home/admin/flutter/bin/flutter pub get

# Run web
cd frontend && /home/admin/flutter/bin/flutter run -d chrome --web-port=8080

# Analyze
cd frontend && /home/admin/flutter/bin/flutter analyze

# Format
cd frontend && /home/admin/flutter/bin/dart format lib/
```

## Key Files to Know
- `backend/services/chat_service.py` - Chat orchestration with persistence
- `backend/services/aliyun_ai_service.py` - LLM integration
- `backend/services/memory_service.py` - Vector memory storage/retrieval
- `backend/services/emotion_service.py` - Emotion state machine
- `backend/models/` - All database models
- `frontend/lib/features/chat/chat_page.dart` - Main chat UI

## Database
- SQLite at `backend/soulpulse.db`
- Key tables: users, ai_personas, user_ai_interactions, emotion_states, memories, relational_anchors, chat_messages, chat_summaries, proactive_dms

## Environment Variables
Backend requires `.env` file with:
- `DASHSCOPE_API_KEY` - Aliyun AI API key
- `SECRET_KEY` - JWT signing key

## Testing Notes
- Backend tests in `backend/tests/`
- Use `pytest -v` for verbose output
- Frontend: use `flutter test` for widget tests

## Code Conventions
- Python: PEP 8, async/await for DB operations
- Dart: Effective Dart style guide
- All API endpoints return JSON with consistent error format
