#!/bin/bash
# SoulPulse Admin Dashboard - runs on separate port 8002
# Usage: ./run_admin.sh [--daemon]

cd /home/admin/Documents/SoulPulse/backend

if [ "$1" == "--daemon" ]; then
    nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8002 > /var/log/soulpulse_admin.log 2>&1 &
    echo $! > /var/run/soulpulse_admin.pid
    echo "Admin dashboard started on port 8002 (PID: $(cat /var/run/soulpulse_admin.pid))"
else
    python3 -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload
fi