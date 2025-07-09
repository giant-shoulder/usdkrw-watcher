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

async def get_bounce_probability_from_rates(conn, lower_bound: float) -> float:
    """
    볼린저 밴드 하단 이탈 발생 시, 30분 이내 반등(하단 이상 복귀) 확률 계산

    Args:
        conn: PostgreSQL connection
        lower_bound: 당시 기준 하단 값

    Returns:
        반등 확률 (0~100 사이의 소수점 포함 백분율)
    """
    query = """
        WITH lower_breaks AS (
          SELECT
            r1.timestamp AS break_time,
            r1.value AS break_value
          FROM rates r1
          WHERE r1.value < $1
        ),
        rebounds AS (
          SELECT
            b.break_time,
            MIN(r2.timestamp) AS rebound_time
          FROM lower_breaks b
          JOIN rates r2
            ON r2.timestamp > b.break_time
           AND r2.timestamp <= b.break_time + INTERVAL '30 minutes'
           AND r2.value >= $1
          GROUP BY b.break_time
        )
        SELECT
          COUNT(*) AS total_breaks,
          COUNT(rebound_time) AS rebound_count
        FROM lower_breaks b
        LEFT JOIN rebounds r ON b.break_time = r.break_time;
    """
    row = await conn.fetchrow(query, lower_bound)
    if row and row["total_breaks"] > 0:
        return round(row["rebound_count"] / row["total_breaks"] * 100, 1)
    return 0.0

async def get_reversal_probability_from_rates(conn, upper_bound: float) -> float:
    """
    볼린저 밴드 상단 돌파 발생 시, 30분 이내 조정(상단 이하 복귀) 확률 계산

    Args:
        conn: PostgreSQL connection
        upper_bound: 당시 기준 상단 값

    Returns:
        조정 확률 (0~100 사이의 소수점 포함 백분율)
    """
    query = """
        WITH upper_breaks AS (
          SELECT
            r1.timestamp AS break_time,
            r1.value AS break_value
          FROM rates r1
          WHERE r1.value > $1
        ),
        corrections AS (
          SELECT
            b.break_time,
            MIN(r2.timestamp) AS correction_time
          FROM upper_breaks b
          JOIN rates r2
            ON r2.timestamp > b.break_time
           AND r2.timestamp <= b.break_time + INTERVAL '30 minutes'
           AND r2.value <= $1
          GROUP BY b.break_time
        )
        SELECT
          COUNT(*) AS total_breaks,
          COUNT(correction_time) AS correction_count
        FROM upper_breaks b
        LEFT JOIN corrections r ON b.break_time = r.break_time;
    """
    row = await conn.fetchrow(query, upper_bound)
    if row and row["total_breaks"] > 0:
        return round(row["correction_count"] / row["total_breaks"] * 100, 1)
    return 0.0