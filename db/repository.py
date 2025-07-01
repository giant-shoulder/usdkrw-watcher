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