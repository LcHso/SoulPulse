"""Create or update admin user.

Usage:
    python3 scripts/create_admin.py                    # Interactive
    python3 scripts/create_admin.py email pass123      # Command line
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session, init_db
from models.user import User
from core.security import hash_password
from sqlalchemy import select


async def create_admin(email: str = None, password: str = None):
    """Create admin user or promote existing user to admin."""
    await init_db()

    async with async_session() as db:
        # Check if admin already exists
        result = await db.execute(select(User).where(User.is_admin == 1))
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            print(f"[create_admin] Admin already exists: {existing_admin.email}")
            print(f"                 ID: {existing_admin.id}")
            return existing_admin

        # If no email provided, use interactive mode
        if not email:
            email = input("Enter admin email: ").strip()
            password = input("Enter admin password: ").strip()

        if not email or not password:
            print("[create_admin] Email and password required!")
            return None

        # Check if user with this email exists
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            # Promote existing user to admin
            existing_user.is_admin = 1
            await db.commit()
            print(f"[create_admin] Promoted existing user to admin: {email}")
            print(f"                 ID: {existing_user.id}")
            return existing_user

        # Create new admin user
        admin = User(
            email=email,
            hashed_password=hash_password(password),
            nickname="Admin",
            is_admin=1,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        print(f"[create_admin] Created new admin user: {email}")
        print(f"                 ID: {admin.id}")
        print(f"                 Password: {'*' * len(password)}")
        return admin


if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else None
    password = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(create_admin(email, password))