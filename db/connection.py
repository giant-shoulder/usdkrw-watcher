import asyncpg
from config import DB_URL, DB_URL_MASKED


async def connect_to_db():
    """
    Supabase PostgreSQL 연결 함수
    """
    print(f"📡 DB 연결 시도 중: {DB_URL_MASKED}")
    try:
        # Test connection
        conn = await asyncpg.connect(dsn=DB_URL, statement_cache_size=0)
        print("✅ DB 연결 성공")
        return conn
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        raise


async def close_db_connection(conn):
    """
    Supabase PostgreSQL 연결 종료 함수
    """
    if conn:
        await conn.close()
        print("✅ DB 연결 종료")