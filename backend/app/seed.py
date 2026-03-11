"""Seed database with default admin users.

Categories & options are now defined in categories.json (static file)
and no longer need database seeding.
"""
from sqlalchemy.orm import Session
from app.config import settings
from app.models.user import User
from app.services.auth import hash_password


def seed_database(db: Session):
    """Seed admin users from environment config."""

    for admin_data in settings.seed_admins_list:
        username = admin_data.get("username")
        password = admin_data.get("password")
        full_name = admin_data.get("full_name", "")
        if not username or not password:
            print("[SEED] Skipping admin entry with missing username or password")
            continue
        existing = db.query(User).filter(User.username == username).first()
        if not existing:
            admin = User(
                username=username,
                password_hash=hash_password(password),
                full_name=full_name,
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print(f"[SEED] Created admin user: {username}")
        else:
            print(f"[SEED] Admin user already exists: {username}")
