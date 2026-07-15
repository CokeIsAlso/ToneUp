"""analysis.py의 신호처리/텍스트 분석 헬퍼 단위 테스트.

Whisper는 지연 로딩이므로 이 테스트들은 모델을 적재하지 않는다.
"""

import numpy as np
from toneup.services import analysis


def test_count_habit_words_exact_token_match():
    # 부분 문자열이 아닌 '독립 단어'로 쓰인 습관어만 세어야 한다.
    words = "어 그 저는 어떻게 그래서 음 좀 빠르게 말했어요".split()
    result = {h["word"]: h["count"] for h in analysis._count_habit_words(words)}
    assert result["어"] == 1   # '어떻게','말했어요'의 '어'는 세지 않음
    assert result["그"] == 1   # '그래서'의 '그'는 세지 않음
    assert result["좀"] == 1
    assert result["저"] == 0   # '저는'은 토큰이 '저는'이라 매칭 안 됨


def test_count_habit_words_strips_punctuation():
    words = ["어,", "음.", "그!"]
    result = {h["word"]: h["count"] for h in analysis._count_habit_words(words)}
    assert result["어"] == 1
    assert result["음"] == 1
    assert result["그"] == 1


def test_analyze_pauses_detects_silence_gap():
    sr = 16000
    tone = 0.3 * np.sin(2 * np.pi * 150 * np.arange(sr) / sr)  # 1초 발화
    silence = np.zeros(sr)  # 1초 무음
    audio = np.concatenate([tone, silence, tone]).astype(np.float32)
    count, seconds = analysis._analyze_pauses(audio, sr)
    assert count == 1
    assert seconds > 0.5


def test_analyze_pauses_empty():
    assert analysis._analyze_pauses(np.array([], dtype=np.float32), 16000) == (0, 0.0)


def test_analyze_pitch_monotone_for_pure_tone():
    sr = 16000
    t = np.arange(2 * sr) / sr
    audio = (0.3 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    res = analysis._analyze_pitch(audio, sr)
    assert res["pitch_label"] in ("단조로움", "적절한 억양", "풍부한 억양")
    # 순음은 음정 변화가 거의 없어 단조로워야 한다.
    assert res["pitch_range"] < 2.5
    assert 120 < res["pitch_mean"] < 180


def test_analyze_volume_structure_and_consistency():
    sr = 16000
    t = np.arange(2 * sr) / sr
    audio = (0.3 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    res = analysis._analyze_volume(audio, sr)
    assert res["volume_label"] in ("작음", "적절", "큼")
    assert 0 <= res["volume_consistency"] <= 100
    # 진폭이 일정한 사인파는 음량 일관성이 높아야 한다.
    assert res["volume_consistency"] > 70


def test_analyze_volume_empty():
    res = analysis._analyze_volume(np.array([], dtype=np.float32), 16000)
    assert res["volume_label"] == "분석 불가"


def test_analyze_emotion_structure_and_range():
    pitch = {"pitch_range": 5.0}
    volume = {"volume_db": -18.0}
    res = analysis._analyze_emotion(pitch, volume, sps=3.5, pause_ratio=10.0)
    assert 0 <= res["energy"] <= 100
    assert res["emotion_label"] in {"활기참", "가라앉음", "단조로움", "다소 긴장됨", "안정적"}


def test_analyze_segments_basic():
    segs = [
        {"start": 0.0, "end": 2.0, "text": " 안녕하세요 ", "avg_logprob": -0.2},
        {"start": 2.5, "end": 5.0, "text": "발표를 시작하겠습니다", "avg_logprob": -0.6},
        {"start": 5.0, "end": 5.5, "text": "  "},  # 빈 텍스트는 제외
    ]
    out = analysis._analyze_segments(segs)
    assert len(out) == 2
    first = out[0]
    assert first["text"] == "안녕하세요"
    assert first["sps"] == 2.5  # 5음절 / 2초
    assert first["clarity"] == 80  # (1 - 0.2) * 100
    assert out[1]["clarity"] == 40
    # 모든 구간이 필수 키를 가진다
    for s in out:
        assert {"start", "end", "text", "sps", "clarity"} <= set(s)


def test_overall_score_range_and_ordering():
    good = analysis._overall_score(
        pron_score=90, sps=3.5, total_habits=0, duration=60,
        pause_ratio=15.0, pitch_range=5.0,
    )
    bad = analysis._overall_score(
        pron_score=40, sps=7.0, total_habits=20, duration=60,
        pause_ratio=60.0, pitch_range=0.5,
    )
    assert 0 <= bad < good <= 100
    assert good >= 90  # 전 지표가 이상적이면 높은 점수


def test_analyze_emotion_monotone_low_energy():
    # 음정 변화 거의 없고 음량 작음 → 낮은 에너지/단조로움 계열
    res = analysis._analyze_emotion(
        {"pitch_range": 0.5}, {"volume_db": -45.0}, sps=2.0, pause_ratio=40.0
    )
    assert res["energy"] <= 35
    assert res["emotion_label"] in {"가라앉음", "단조로움"}
