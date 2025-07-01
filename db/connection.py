import asyncpg
from config import DB_URL, DB_URL_MASKED


async def connect_to_db():
    """
    Supabase PostgreSQL 연결 함수
    """
    print(f"📡 DB 연결 시도 중: {DB_URL_MASKED}")
    conn = await asyncpg.connect(dsn=DB_URL, statement_cache_size=0)
    return conn