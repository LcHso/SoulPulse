# SoulPulse Deployment Guide

## Required GitHub Secrets

Configure these in **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `SSH_PRIVATE_KEY` | ECS SSH private key for `admin@123.57.227.61` |
| `DASHSCOPE_API_KEY` | Aliyun Qwen API key for AI services |
| `PG_PASSWORD` | PostgreSQL database password |
| `SECRET_KEY` | JWT signing key for backend authentication |

## Branch Strategy

| Branch | Environment | Port | Compose File |
|--------|-------------|------|--------------|
| `main` | Production | 80 | `docker-compose.prod.yml` |
| `develop` | Test | 9080 | `docker-compose.test.yml` |

- Push to `main` → auto-deploys to **production**
- Push to `develop` → auto-deploys to **test**
- Pull requests to either branch trigger the **test** workflow (lint + unit tests)

## Deployment Methods

### Automatic (GitHub Actions)

Push to `main` or `develop` triggers the deploy workflow automatically.

### Manual via GitHub UI

1. Go to **Actions → Deploy SoulPulse → Run workflow**
2. Select branch and target environment (`prod` or `test`)
3. Click **Run workflow**

### Manual via SSH

```bash
ssh admin@123.57.227.61
cd /home/admin/Documents/SoulPulse
git pull origin main
./deploy-env.sh prod   # or: ./deploy-env.sh test
```

## Workflow Overview

The deploy workflow executes in this order:

1. **Build locally** (on GitHub runner) — admin frontend (npm) + Flutter web
2. **SSH to server** — pull latest code, run `deploy-env.sh` (builds Docker images, restarts backend services)
3. **SCP frontend builds** — sync `frontend/build/web/` and `admin-frontend/dist/` to server
4. **Restart nginx** — picks up new static frontend files

## Troubleshooting

- **Health check failing**: SSH into server and check `docker compose logs nginx` / `docker compose logs backend`
- **Flutter build fails in CI**: Ensure `pubspec.lock` is committed and Flutter version matches (`3.27.0`)
- **SSH connection refused**: Verify the `SSH_PRIVATE_KEY` secret is set correctly and the server firewall allows port 22
