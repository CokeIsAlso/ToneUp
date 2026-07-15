"""database CRUD, 사용자별 스코프, 통계, 마이그레이션 테스트."""

import pytest
from toneup import db as database

USER = 1
OTHER = 2


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.init_db()
    return db_file


def _sample(text="안녕하세요 발표 연습"):
    return {
        "text": text,
        "duration": 5.2,
        "word_count": 3,
        "syllables": 9,
        "wpm": 80,
        "sps": 3.5,
        "speed_label": "적절한 속도",
        "pron_score": 82,
        "total_habits": 1,
        "pause_count": 1,
        "pause_ratio": 12.0,
        "pitch_mean": 145.0,
        "pitch_range": 4.2,
        "pitch_label": "적절한 억양",
        "volume_db": -18.0,
        "volume_consistency": 85,
        "volume_label": "적절",
        "emotion_label": "안정적",
        "energy": 62,
        "mode": "free",
        "habits": [{"word": "어", "count": 1}],
        "feedback": ["말 속도가 적절합니다!"],
        "ai_coaching": None,
        "ai_improved": None,
    }


def test_save_and_get(temp_db):
    rid = database.save_record(_sample(), USER)
    rec = database.get_record(rid, USER)
    assert rec["text"] == "안녕하세요 발표 연습"
    assert rec["pron_score"] == 82
    assert rec["emotion_label"] == "안정적"
    assert rec["habits"] == [{"word": "어", "count": 1}]
    assert rec["feedback"] == ["말 속도가 적절합니다!"]
    # 타인은 접근 불가
    assert database.get_record(rid, OTHER) is None


def test_records_scoped_by_user(temp_db):
    database.save_record(_sample("내 것1"), USER)
    database.save_record(_sample("내 것2"), USER)
    database.save_record(_sample("남의 것"), OTHER)
    assert len(database.list_records(USER)) == 2
    assert len(database.list_records(OTHER)) == 1
    assert database.list_records(USER)[0]["text"] == "내 것2"  # 최신순


def test_get_missing_returns_none(temp_db):
    assert database.get_record(999, USER) is None


def test_delete_record_scoped(temp_db):
    rid = database.save_record(_sample(), USER)
    assert database.delete_record(rid, OTHER) is False  # 타인은 삭제 불가
    assert database.delete_record(rid, USER) is True
    assert database.get_record(rid, USER) is None


def test_get_stats_empty(temp_db):
    assert database.get_stats(USER) == {"sessions": 0}


def test_get_stats_aggregates_per_user(temp_db):
    s1 = _sample("첫 세션"); s1["pron_score"] = 70
    database.save_record(s1, USER)
    s2 = _sample("둘째 세션"); s2["pron_score"] = 90
    database.save_record(s2, USER)
    database.save_record(_sample("타인"), OTHER)  # 다른 유저는 통계에 미포함

    stats = database.get_stats(USER)
    assert stats["sessions"] == 2
    assert stats["best_pron"] == 90
    assert stats["first_pron"] == 70
    assert stats["latest_pron"] == 90
    assert stats["improvement"] == 20


def test_user_index_created(temp_db):
    import sqlite3

    conn = sqlite3.connect(temp_db)
    names = {r[1] for r in conn.execute("PRAGMA index_list(records)")}
    conn.close()
    assert "idx_records_user_id" in names


def test_user_crud(temp_db):
    uid = database.create_user("x@y.com", "hash")
    assert uid
    assert database.create_user("x@y.com", "hash2") is None  # 중복 이메일
    assert database.get_user_by_email("x@y.com")["id"] == uid
    assert database.get_user_by_id(uid)["email"] == "x@y.com"


def test_calc_streak():
    from datetime import date

    today = date(2026, 7, 15)
    # 오늘 포함 3일 연속
    assert database._calc_streak(["2026-07-15", "2026-07-14", "2026-07-13"], today) == 3
    # 어제까지 연속(오늘 아직 안 함)도 유지
    assert database._calc_streak(["2026-07-14", "2026-07-13"], today) == 2
    # 이틀 전이 마지막이면 스트릭 끊김
    assert database._calc_streak(["2026-07-12", "2026-07-11"], today) == 0
    # 중간에 빈 날이 있으면 거기까지만
    assert database._calc_streak(["2026-07-15", "2026-07-13"], today) == 1
    # 빈 목록 / 잘못된 형식은 0
    assert database._calc_streak([], today) == 0
    assert database._calc_streak(["invalid"], today) == 0


def test_stats_include_streak_and_overall(temp_db):
    s = _sample()
    s["overall_score"] = 77
    database.save_record(s, USER)
    stats = database.get_stats(USER)
    assert stats["streak"] == 1  # 오늘 저장했으므로
    assert stats["avg_overall"] == 77.0


def test_migration_adds_missing_columns(tmp_path, monkeypatch):
    import sqlite3

    db_file = tmp_path / "old.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE records (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "created_at TEXT, text TEXT)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.init_db()  # 신규 컬럼 + users 테이블 생성
    rid = database.save_record(_sample(), USER)
    rec = database.get_record(rid, USER)
    assert rec["pitch_label"] == "적절한 억양"
    assert rec["energy"] == 62
