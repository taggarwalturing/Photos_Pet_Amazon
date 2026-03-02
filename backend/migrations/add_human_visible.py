"""
Add human_visible tracking columns to images table
Run this script to update your existing database with human visibility features
"""
from sqlalchemy import create_engine
from sqlalchemy.sql import text
import os

# Get database URL from env or use default
database_url = os.getenv('DATABASE_URL', 'sqlite:///./photo_annotation.db')

# Create engine
engine = create_engine(database_url)

def migrate():
    """Add human visibility columns to images table"""
    print("🔄 Adding human visibility columns to images table...")
    
    with engine.begin() as conn:
        try:
            # Check if columns already exist
            result = conn.execute(text("SELECT * FROM images LIMIT 1"))
            existing_columns = result.keys()
            
            if 'human_visible' not in existing_columns:
                print("  ✓ Adding human_visible column...")
                conn.execute(text("""
                    ALTER TABLE images 
                    ADD COLUMN human_visible BOOLEAN
                """))
            
            if 'human_visible_marked_by' not in existing_columns:
                print("  ✓ Adding human_visible_marked_by column...")
                conn.execute(text("""
                    ALTER TABLE images 
                    ADD COLUMN human_visible_marked_by INTEGER
                """))
                
                # Add foreign key constraint for PostgreSQL
                if not database_url.startswith('sqlite'):
                    conn.execute(text("""
                        ALTER TABLE images 
                        ADD CONSTRAINT fk_human_visible_marked_by 
                        FOREIGN KEY (human_visible_marked_by) REFERENCES users(id)
                    """))
            
            if 'human_visible_marked_at' not in existing_columns:
                print("  ✓ Adding human_visible_marked_at column...")
                conn.execute(text("""
                    ALTER TABLE images 
                    ADD COLUMN human_visible_marked_at TIMESTAMP
                """))
            
            print("\n✅ Migration completed successfully!")
            print("\nNew columns:")
            print("  - human_visible: Boolean (True=Visible, False=Not Visible, NULL=Unknown)")
            print("  - human_visible_marked_by: User ID who marked it")
            print("  - human_visible_marked_at: Timestamp of marking")
            
        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            print("\nNote: If columns already exist, this is normal.")
            raise

if __name__ == "__main__":
    print("=" * 70)
    print("DATABASE MIGRATION: Add Human Visibility Columns")
    print("=" * 70)
    print()
    
    try:
        migrate()
        print("\n🎉 All done!")
    except Exception as e:
        print(f"\n⚠️  Migration encountered an issue. Check the error above.")
        exit(1)
