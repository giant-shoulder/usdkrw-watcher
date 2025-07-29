import asyncpg
from config import DB_URL, DB_URL_MASKED


async def init_db_pool(min_size=1, max_size=5):
    """
    DB 커넥션 풀 초기화 (명시적 반환)
    """
    print(f"📡 DB 풀 초기화 중: {DB_URL_MASKED}")
    try:
        db_pool = await asyncpg.create_pool(
            dsn=DB_URL,
            min_size=min_size,
            max_size=max_size,
            statement_cache_size=0,
            timeout=10
        )
        print("✅ DB 풀 초기화 완료")
        return db_pool
    except Exception as e:
        print(f"❌ DB 풀 초기화 실패: {e}")
        raise


async def close_db_pool(pool):
    """
    DB 커넥션 풀 종료
    """
    if pool:
        await pool.close()
        print("✅ DB 풀 종료 완료")
        

async def fetch_rows(query: str, *args):
    """
    쿼리 실행 후 결과 fetch
    """
    global db_pool
    if db_pool is None:
        raise RuntimeError("DB 풀이 초기화되지 않았습니다.")
    
    async with db_pool.acquire() as conn:
        try:
            async with conn.transaction():
                rows = await conn.fetch(query, *args)
                return [(row["timestamp"], row["rate"]) for row in rows]
        except Exception as e:
            print(f"❌ 쿼리 실행 실패: {e}")
            raise