from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings


def _ensure_database_exists():
    """Create the database if it doesn't exist yet."""
    # Only needed for PostgreSQL, SQLite creates the file automatically
    if not settings.DATABASE_URL.startswith("sqlite"):
        # Parse the target DB name from the URL
        # Format: postgresql://user:pass@host:port/dbname
        base_url = settings.DATABASE_URL.rsplit("/", 1)[0]
        db_name = settings.DATABASE_URL.rsplit("/", 1)[1]

        # Connect to the default 'postgres' database to check/create
        tmp_engine = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
        with tmp_engine.connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            )
            if not result.fetchone():
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print(f"[DB] Created database '{db_name}'")
        tmp_engine.dispose()


_ensure_database_exists()

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
