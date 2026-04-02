# SoulPulse Developer Console (SDC) - Implementation Spec

## Overview
Admin dashboard for managing SoulPulse AI companion platform.

## Architecture

### Backend Changes

#### 1. Database Schema Updates

**User Model Extension** (`backend/models/user.py`)
```python
# Add to existing User model:
role: Mapped[str] = mapped_column(String(20), default="user")  # "user" | "admin"
is_active: Mapped[bool] = mapped_column(Boolean, default=True)
last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

**New Admin-Only Tables**
- `audit_logs` - Track admin actions
- `system_config` - Global configuration key-value store
- `api_usage_logs` - Track API consumption

#### 2. New API Endpoints

**Admin Auth Middleware** (`backend/core/admin_auth.py`)
- Require `role == "admin"` for all `/admin/*` endpoints
- Log all admin actions to `audit_logs`

**Admin Endpoints** (`backend/api/endpoints/admin.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/stats/overview` | GET | Dashboard overview stats |
| `/admin/stats/retention` | GET | User retention funnel |
| `/admin/stats/api-usage` | GET | API consumption metrics |
| `/admin/users` | GET | List users with filters |
| `/admin/users/{id}` | GET | User detail |
| `/admin/users/{id}/ban` | POST | Ban/unban user |
| `/admin/personas` | GET/PUT | Manage AI personas |
| `/admin/personas/{id}/emotion` | GET | View emotion state |
| `/admin/personas/{id}/portrait` | POST | Regenerate base portrait |
| `/admin/memories` | GET | Search/audit memories |
| `/admin/memories/{id}` | DELETE | Remove problematic memory |
| `/admin/posts` | GET/DELETE | Manage feed posts |
| `/admin/posts/generate` | POST | Trigger content generation |
| `/admin/config` | GET/PUT | System configuration |
| `/admin/audit-logs` | GET | View admin action history |

### Frontend Structure

**Admin Module** (`frontend/lib/features/admin/`)
```
admin/
├── admin_shell.dart          # Main admin layout with sidebar
├── dashboard_page.dart      # Analytics overview
├── users_page.dart           # User management
├── personas_page.dart        # AI persona editor
├── memories_page.dart        # Memory audit
├── content_page.dart         # Posts/stories management
├── settings_page.dart        # System config
└── components/
    ├── stat_card.dart
    ├── data_table.dart
    └── chart_widgets.dart
```

## Implementation Phases

### Phase 1: Foundation
1. Add `role` field to User model + migration
2. Create admin authentication middleware
3. Create base admin endpoint structure
4. Add admin role to initial admin user

### Phase 2: Analytics Dashboard
1. Stats overview API (users, messages, DAU/MAU)
2. Retention funnel calculation
3. API usage tracking
4. Dashboard UI with charts

### Phase 3: Core Management
1. User management (list, search, ban)
2. Persona editor (prompts, visual tags, emotions)
3. Memory audit (search, view, delete)

### Phase 4: Content Operations
1. Post management (list, delete, regenerate)
2. Batch content generation
3. Story asset management

### Phase 5: Advanced Features
1. Audit log viewer
2. System configuration editor
3. A/B test management (future)

## Security Considerations
- All admin endpoints require JWT + role verification
- Sensitive actions logged to audit_logs
- Rate limiting on admin endpoints
- IP whitelist option for production

## Route Protection
```dart
// In app router
GoRoute(
  path: '/admin',
  builder: (context, state) => const AdminShell(),
  redirect: (context, state) {
    final user = ref.read(authProvider);
    if (user?.role != 'admin') return '/login';
    return null;
  },
)
```