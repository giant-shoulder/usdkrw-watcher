from datetime import datetime
import pytz

async def store_rate(conn, rate: float):
    """
    DB에 환율 저장
    """
    now = datetime.now(pytz.timezone("Asia/Seoul"))
    await conn.execute("INSERT INTO rates (timestamp, rate) VALUES ($1, $2)", now, rate)


async def get_recent_rates(conn, limit: int):
    """
    최신 환율 데이터 조회 (가장 오래된 순으로 반환)
    """
    rows = await conn.fetch(
        "SELECT rate FROM rates ORDER BY timestamp DESC LIMIT $1", limit
    )
    return [r["rate"] for r in reversed(rows)]

async def store_expected_range(conn, date, low: float, high: float, source: str):
    """
    예상 환율 범위를 DB에 저장 (동일 날짜는 업데이트)
    """
    await conn.execute(
        """
        INSERT INTO expected_ranges (date, low, high, source)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (date) DO UPDATE
        SET low = EXCLUDED.low,
            high = EXCLUDED.high,
            source = EXCLUDED.source
        """,
        date, low, high, source
    )

async def get_today_expected_range(conn):
    """
    오늘 날짜의 예상 환율 범위를 조회합니다.
    """
    today = datetime.now(pytz.timezone("Asia/Seoul")).date()
    row = await conn.fetchrow(
        "SELECT date, low, high, source FROM expected_ranges WHERE date = $1", today
    )
    if row:
        return {
            "date": row["date"],
            "low": row["low"],
            "high": row["high"],
            "source": row["source"]
        }
    return None