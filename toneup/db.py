"""분석 결과를 SQLite에 저장/조회하는 데이터 액세스 계층.

스키마는 :data:`_COLUMNS`로 한 곳에서 정의하며, 컬럼을 추가하면
:func:`init_db`가 기존 DB에 자동으로 `ALTER TABLE`을 적용(마이그레이션)한다.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Iterator, Optional

logger = logging.getLogger("toneup")

# 기본 DB 경로 — create_app()에서 Config 값으로 덮어쓴다.
DB_PATH: str = os.environ.get(
    "TONEUP_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "toneup.db")
)

# 저장 컬럼 정의 (이름 -> SQL 타입).
_COLUMNS: dict[str, str] = {
    "user_id": "INTEGER",
    "created_at": "TEXT",
    "text": "TEXT",
    "duration": "REAL",
    "word_count": "INTEGER",
    "syllables": "INTEGER",
    "wpm": "INTEGER",
    "sps": "REAL",
    "speed_label": "TEXT",
    "pron_score": "INTEGER",
    "overall_score": "INTEGER",
    "total_habits": "INTEGER",
    "pause_count": "INTEGER",
    "pause_ratio": "REAL",
    "pitch_mean": "REAL",
    "pitch_range": "REAL",
    "pitch_label": "TEXT",
    "volume_db": "REAL",
    "volume_consistency": "INTEGER",
    "volume_label": "TEXT",
    "emotion_label": "TEXT",
    "energy": "INTEGER",
    "mode": "TEXT",
    "wav_file": "TEXT",
    "habits": "TEXT",
    "segments": "TEXT",
    "feedback": "TEXT",
    "ai_coaching": "TEXT",
    "ai_improved": "TEXT",
}

_JSON_FIELDS: tuple[str, ...] = ("habits", "segments", "feedback")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """커넥션을 열어 트랜잭션(commit/rollback) 후 반드시 닫는다.

    sqlite3의 기본 컨텍스트 매니저는 commit만 하고 close하지 않아
    커넥션이 누수되므로 명시적으로 close까지 책임진다.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:  # 성공 시 commit, 예외 시 rollback
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    """테이블을 생성하고, 누락된 컬럼이 있으면 추가(마이그레이션)한다."""
    cols_sql = ",\n".join(f"{name} {typ}" for name, typ in _COLUMNS.items())
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users (\n"
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
            "  email TEXT UNIQUE NOT NULL,\n"
            "  password_hash TEXT NOT NULL,\n"
            "  created_at TEXT NOT NULL\n)"
        )
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS records (\n"
            f"  id INTEGER PRIMARY KEY AUTOINCREMENT,\n{cols_sql}\n)"
        )
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(records)")}
        for name, typ in _COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE records ADD COLUMN {name} {typ}")
                logger.info("DB migration: added column %s", name)
        # user별 조회(기록·통계)가 대부분이므로 인덱스로 스캔 방지
        conn.execute("CREATE INDEX IF NOT EXISTS idx_records_user_id ON records(user_id)")


# ----- 사용자 -----

def create_user(email: str, password_hash: str) -> Optional[int]:
    """사용자를 생성하고 id를 반환한다. 이미 있으면 None."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?,?,?)",
                (email, password_hash, datetime.now().isoformat(timespec="seconds")),
            )
            return int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return None


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def save_record(result: dict[str, Any], user_id: int) -> int:
    """분석 결과 dict를 user 소유로 저장하고 새 레코드 id를 반환한다."""
    names = list(_COLUMNS.keys())
    values: list[Any] = []
    for name in names:
        if name == "user_id":
            values.append(user_id)
        elif name == "created_at":
            values.append(datetime.now().isoformat(timespec="seconds"))
        elif name in _JSON_FIELDS:
            values.append(json.dumps(result.get(name, []), ensure_ascii=False))
        else:
            values.append(result.get(name))

    placeholders = ",".join("?" for _ in names)
    with _connect() as conn:
        cur = conn.execute(
            f"INSERT INTO records ({','.join(names)}) VALUES ({placeholders})", values
        )
        return int(cur.lastrowid)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for f in _JSON_FIELDS:
        d[f] = json.loads(d.get(f) or "[]")
    return d


def list_records(user_id: int, limit: int = 30) -> list[dict[str, Any]]:
    """해당 user의 기록을 요약 필드만 최신순으로 반환한다."""
    cols = (
        "id, created_at, text, duration, sps, speed_label, pron_score, overall_score, "
        "total_habits, pause_count, pause_ratio, pitch_range, pitch_label, volume_db, "
        "volume_consistency, emotion_label, energy, mode"
    )
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT {cols} FROM records WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_record(record_id: int, user_id: int) -> Optional[dict[str, Any]]:
    """본인 소유의 단일 레코드 전체를 반환한다. 없거나 타인 것이면 None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM records WHERE id = ? AND user_id = ?", (record_id, user_id)
        ).fetchone()
        return _row_to_dict(row) if row else None


def delete_record(record_id: int, user_id: int) -> bool:
    """본인 소유의 레코드를 삭제한다. 삭제된 게 있으면 True."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM records WHERE id = ? AND user_id = ?", (record_id, user_id)
        )
        return cur.rowcount > 0


def _calc_streak(day_strs: list[str], today: Optional[date] = None) -> int:
    """연습한 날짜(YYYY-MM-DD) 목록에서 '연속 연습 일수'를 계산한다.

    오늘 또는 어제 연습했어야 스트릭이 살아 있는 것으로 본다.
    """
    days: list[date] = []
    for d in set(day_strs):
        try:
            days.append(date.fromisoformat(d))
        except ValueError:
            continue
    if not days:
        return 0
    days.sort(reverse=True)

    today = today or date.today()
    if days[0] not in (today, today - timedelta(days=1)):
        return 0
    streak = 1
    for prev, cur in zip(days, days[1:]):
        if (prev - cur).days == 1:
            streak += 1
        else:
            break
    return streak


def get_stats(user_id: int) -> dict[str, Any]:
    """해당 user의 성장 요약 통계(세션 수·평균/최고 발음·향상도·스트릭 등)."""
    with _connect() as conn:
        agg = conn.execute(
            "SELECT COUNT(*) n, AVG(pron_score) ap, MAX(pron_score) bp, "
            "AVG(sps) asps, AVG(total_habits) ah, AVG(overall_score) ao "
            "FROM records WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        sessions = agg["n"] or 0
        if sessions == 0:
            return {"sessions": 0}

        first = conn.execute(
            "SELECT pron_score FROM records WHERE user_id = ? AND pron_score IS NOT NULL "
            "ORDER BY id ASC LIMIT 1",
            (user_id,),
        ).fetchone()
        last = conn.execute(
            "SELECT pron_score FROM records WHERE user_id = ? AND pron_score IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        first_pron = first["pron_score"] if first else 0
        latest_pron = last["pron_score"] if last else 0

        day_rows = conn.execute(
            "SELECT DISTINCT substr(created_at, 1, 10) d FROM records "
            "WHERE user_id = ? AND created_at IS NOT NULL",
            (user_id,),
        ).fetchall()
        streak = _calc_streak([r["d"] for r in day_rows])

        return {
            "sessions": sessions,
            "avg_pron": round(agg["ap"] or 0, 1),
            "best_pron": agg["bp"] or 0,
            "avg_overall": round(agg["ao"], 1) if agg["ao"] is not None else None,
            "avg_sps": round(agg["asps"] or 0, 2),
            "avg_habits": round(agg["ah"] or 0, 1),
            "first_pron": first_pron,
            "latest_pron": latest_pron,
            "improvement": (latest_pron or 0) - (first_pron or 0),
            "streak": streak,
        }
