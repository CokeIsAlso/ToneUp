"""report.py PDF 생성 테스트."""

from toneup.services import report


def test_build_report_pdf_returns_valid_pdf():
    record = {
        "created_at": "2026-06-25T10:00:00",
        "text": "안녕하세요 발표 연습입니다",
        "duration": 5.2,
        "word_count": 3,
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
        "habits": [{"word": "어", "count": 1}],
        "feedback": ["말 속도가 적절합니다!", "발음이 매우 또렷합니다!"],
        "ai_coaching": "전반적으로 안정적인 발표였습니다.",
    }
    buf = report.build_report_pdf(record)
    data = buf.getvalue()
    assert data[:5] == b"%PDF-"
    assert len(data) > 1000


def test_build_report_pdf_handles_minimal_record():
    # 일부 필드가 비어 있어도 예외 없이 생성되어야 한다.
    buf = report.build_report_pdf({"created_at": "2026-06-25T10:00:00"})
    assert buf.getvalue()[:5] == b"%PDF-"
