"""
Add manual blur tracking columns to images table
Run this script to update your existing database with blur tracking features
"""
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import text
import os
from pathlib import Path

# Get database URL from env or use default
database_url = os.getenv('DATABASE_URL', 'sqlite:///./photo_annotation.db')

# Create engine
engine = create_engine(database_url)

def migrate():
    """Add blur tracking columns to images table"""
    print("🔄 Adding blur tracking columns to images table...")
    
    with engine.begin() as conn:
        try:
            # Check if columns already exist (for SQLite compatibility)
            result = conn.execute(text("SELECT * FROM images LIMIT 1"))
            existing_columns = result.keys()
            
            # Add columns if they don't exist
            if 'manually_blurred' not in existing_columns:
                print("  ✓ Adding manually_blurred column...")
                conn.execute(text("""
                    ALTER TABLE images 
                    ADD COLUMN manually_blurred BOOLEAN DEFAULT FALSE NOT NULL
                """))
            
            if 'blur_regions' not in existing_columns:
                print("  ✓ Adding blur_regions column...")
                # SQLite doesn't have native JSON type, uses TEXT
                if database_url.startswith('sqlite'):
                    conn.execute(text("""
                        ALTER TABLE images 
                        ADD COLUMN blur_regions TEXT
                    """))
                else:
                    conn.execute(text("""
                        ALTER TABLE images 
                        ADD COLUMN blur_regions JSON
                    """))
            
            if 'manually_blurred_by' not in existing_columns:
                print("  ✓ Adding manually_blurred_by column...")
                conn.execute(text("""
                    ALTER TABLE images 
                    ADD COLUMN manually_blurred_by INTEGER
                """))
                
                # Add foreign key constraint for PostgreSQL
                if not database_url.startswith('sqlite'):
                    conn.execute(text("""
                        ALTER TABLE images 
                        ADD CONSTRAINT fk_manually_blurred_by 
                        FOREIGN KEY (manually_blurred_by) REFERENCES users(id)
                    """))
            
            if 'manually_blurred_at' not in existing_columns:
                print("  ✓ Adding manually_blurred_at column...")
                conn.execute(text("""
                    ALTER TABLE images 
                    ADD COLUMN manually_blurred_at TIMESTAMP
                """))
            
            if 'annotated_blur_url' not in existing_columns:
                print("  ✓ Adding annotated_blur_url column...")
                conn.execute(text("""
                    ALTER TABLE images 
                    ADD COLUMN annotated_blur_url TEXT
                """))
            
            print("\n✅ Migration completed successfully!")
            print("📁 Blur tracking columns have been added to the images table.")
            print("\nNew columns:")
            print("  - manually_blurred: Boolean flag")
            print("  - blur_regions: JSON array of blur coordinates")
            print("  - manually_blurred_by: User ID who applied blur")
            print("  - manually_blurred_at: Timestamp of blur application")
            print("  - annotated_blur_url: URL to the blurred image file")
            
        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            print("\nNote: If columns already exist, this is normal.")
            print("If you see other errors, please check your database connection.")
            raise

if __name__ == "__main__":
    print("="*70)
    print("DATABASE MIGRATION: Add Blur Tracking Columns")
    print("="*70)
    print()
    
    try:
        migrate()
        print("\n🎉 All done! Your database is ready to use blur tracking features.")
    except Exception as e:
        print(f"\n⚠️  Migration encountered an issue. Check the error above.")
        exit(1)
