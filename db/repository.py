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

async def get_bounce_probability_from_rates(
    conn,
    lower_bound: float,
    deviation: float,
    tolerance: float,
    moving_average_period: int
) -> float:
    """
    볼린저 밴드 하단에서 일정 금액 이탈한 경우,
    과거 동일한 이탈 폭 범위 조건에서 30분 내 반등 확률 계산

    Args:
        conn: PostgreSQL connection
        lower_bound: 당시 하단 밴드 값
        deviation: 하단 대비 이탈 폭 (예: 0.12)
        tolerance: 허용 오차 범위 (예: 0.02)
        moving_average_period: 이동 평균 계산에 사용할 기간 (데이터 포인트 수)

    Returns:
        반등 확률 (0~100 사이 소수점 포함 백분율)
    """
    query = f"""
        WITH params AS (
          SELECT $1::double precision AS lower_bound,
                 $2::double precision AS deviation,
                 $3::double precision AS tolerance
        ),
        bollinger_calc AS (
          SELECT
            r.timestamp,
            r.rate,
            AVG(r.rate) OVER w AS ma,
            STDDEV_SAMP(r.rate) OVER w AS std
          FROM rates r
          WINDOW w AS (
            ORDER BY r.timestamp
            ROWS BETWEEN {moving_average_period - 1} PRECEDING AND CURRENT ROW
          )
        ),
        lower_breaks AS (
          SELECT
            b.timestamp AS break_time,
            b.rate,
            (b.ma - 2 * b.std) AS lower_band,
            (b.ma - 2 * b.std) - b.rate AS actual_deviation
          FROM bollinger_calc b, params p
          WHERE b.std IS NOT NULL
            AND (b.ma - 2 * b.std) - b.rate BETWEEN p.deviation - p.tolerance AND p.deviation + p.tolerance
            AND b.timestamp >= NOW() - INTERVAL '90 days'
        ),
        rebounds AS (
          SELECT
            b.break_time,
            MIN(r2.timestamp) AS rebound_time
          FROM lower_breaks b
          JOIN rates r2
            ON r2.timestamp > b.break_time
           AND r2.timestamp <= b.break_time + INTERVAL '30 minutes'
           AND r2.rate >= b.lower_band
          GROUP BY b.break_time
        )
        SELECT
          COUNT(*) AS total_matched,
          COUNT(r.rebound_time) AS rebound_count
        FROM lower_breaks b
        LEFT JOIN rebounds r ON b.break_time = r.break_time;
    """
    row = await conn.fetchrow(query, lower_bound, deviation, tolerance)
    if row and row["total_matched"] > 0:
        return round(row["rebound_count"] / row["total_matched"] * 100, 1)
    return 0.0


async def get_reversal_probability_from_rates(
    conn,
    upper_bound: float,
    deviation: float,
    tolerance: float,
    moving_average_period: int
) -> float:
    """
    볼린저 밴드 상단에서 일정 금액 돌파한 경우,
    과거 동일한 초과 폭 범위 조건에서 30분 내 조정 확률 계산

    Args:
        conn: PostgreSQL connection
        upper_bound: 당시 상단 밴드 값
        deviation: 상단 대비 초과 폭 (예: 0.12)
        tolerance: 허용 오차 범위 (예: 0.02)
        moving_average_period: 이동 평균 계산에 사용할 기간 (데이터 포인트 수)

    Returns:
        조정 확률 (0~100 사이 소수점 포함 백분율)
    """
    query = f"""
        WITH params AS (
          SELECT $1::double precision AS upper_bound,
                 $2::double precision AS deviation,
                 $3::double precision AS tolerance
        ),
        bollinger_calc AS (
          SELECT
            r.timestamp,
            r.rate,
            AVG(r.rate) OVER w AS ma,
            STDDEV_SAMP(r.rate) OVER w AS std
          FROM rates r
          WINDOW w AS (
            ORDER BY r.timestamp
            ROWS BETWEEN {moving_average_period - 1} PRECEDING AND CURRENT ROW
          )
        ),
        upper_breaks AS (
          SELECT
            b.timestamp AS break_time,
            b.rate,
            (b.ma + 2 * b.std) AS upper_band,
            b.rate - (b.ma + 2 * b.std) AS actual_deviation
          FROM bollinger_calc b, params p
          WHERE b.std IS NOT NULL
            AND b.rate - (b.ma + 2 * b.std) BETWEEN p.deviation - p.tolerance AND p.deviation + p.tolerance
            AND b.timestamp >= NOW() - INTERVAL '90 days'
        ),
        corrections AS (
          SELECT
            b.break_time,
            MIN(r2.timestamp) AS correction_time
          FROM upper_breaks b
          JOIN rates r2
            ON r2.timestamp > b.break_time
           AND r2.timestamp <= b.break_time + INTERVAL '30 minutes'
           AND r2.rate <= b.upper_band
          GROUP BY b.break_time
        )
        SELECT
          COUNT(*) AS total_matched,
          COUNT(r.correction_time) AS correction_count
        FROM upper_breaks b
        LEFT JOIN corrections r ON b.break_time = r.break_time;
    """
    row = await conn.fetchrow(query, upper_bound, deviation, tolerance)
    if row and row["total_matched"] > 0:
        return round(row["correction_count"] / row["total_matched"] * 100, 1)
    return 0.0


async def insert_breakout_event(conn, event_type: str, timestamp: datetime, boundary: float, threshold: float):
    """
    breakout_events 테이블에 이벤트 기록
    """
    await conn.execute(
        """
        INSERT INTO breakout_events (event_type, timestamp, boundary, threshold)
        VALUES ($1, $2, $3, $4)
        """,
        event_type, timestamp, boundary, threshold
    )


async def get_recent_breakout_events(conn, cutoff_time):
    return await conn.fetch(
        """
        SELECT id, event_type, timestamp, boundary, threshold, resolved
        FROM breakout_events
        WHERE timestamp >= $1
        ORDER BY timestamp ASC
        """,
        cutoff_time
    )


async def get_pending_breakouts(conn) -> list[dict]:
    """
    아직 해결되지 않은 최근 30분 이내 이벤트 불러오기
    """
    query = """
        SELECT id, event_type, timestamp, boundary, threshold
        FROM breakout_events
        WHERE resolved = FALSE
          AND timestamp >= NOW() - INTERVAL '30 minutes'
        ORDER BY timestamp ASC
    """
    return await conn.fetch(query)


async def mark_breakout_resolved(conn, event_id: int) -> None:
    """
    breakout 이벤트를 해결(resolved) 상태로 변경
    """
    query = """
        UPDATE breakout_events
        SET resolved = TRUE, resolved_at = NOW()
        WHERE id = $1
    """
    await conn.execute(query, event_id)


async def get_recent_rates_for_summary(conn, since: datetime) -> list[tuple[datetime, float]]:
    """
    최근 특정 시간 범위(예: 30분) 동안의 환율 데이터 조회
    """
    rows = await conn.fetch(
        """
        SELECT timestamp, rate
        FROM rates
        WHERE timestamp >= $1
        ORDER BY timestamp ASC
        """,
        since
    )
    return [(r["timestamp"], r["rate"]) for r in rows]


async def get_rates_in_block(conn, start: datetime, end: datetime) -> list[tuple[datetime, float]]:
    """
    지정된 시작~종료 시간 블록 내 환율 데이터 조회
    """
    rows = await conn.fetch(
        """
        SELECT timestamp, rate
        FROM rates
        WHERE timestamp >= $1 AND timestamp < $2
        ORDER BY timestamp ASC
        """,
        start, end
    )
    return [(r["timestamp"], r["rate"]) for r in rows]
