import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from app.db.base import Base

logger = logging.getLogger(__name__)

def migrate_db(engine: Engine):
    """
    Ensures new tables and columns exist in the database without breaking existing data.
    """
    logger.info("[Migration] Checking and running schema migrations...")
    # 1. Create any missing tables
    Base.metadata.create_all(bind=engine)

    # 2. Check and add slot_key column to checkins if missing
    inspector = inspect(engine)
    if "checkins" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("checkins")]
        if "slot_key" not in columns:
            logger.info("[Migration] Adding missing 'slot_key' column to 'checkins' table...")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE checkins ADD COLUMN slot_key VARCHAR(100)"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_checkins_slot_key ON checkins(slot_key)"))
            logger.info("[Migration] 'slot_key' column added successfully.")

    logger.info("[Migration] Database migration completed.")
