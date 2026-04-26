from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True, isolation_level="READ UNCOMMITTED")

# This makes sure we are doing a read-only database view
@event.listens_for(engine, "connect")
def set_read_only(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("SET SESSION TRANSACTION READ ONLY")
    cursor.close()

ReadOnlySession = sessionmaker(bind=engine)