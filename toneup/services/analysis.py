"""음성 분석 서비스.

Whisper(STT)와 librosa(신호처리)로 발화 텍스트, 말속도, 발음 점수, 습관어,
휴지(pause), 음정(pitch), 음량(volume)을 분석하고 코칭 피드백을 생성한다.

Whisper 모델은 무겁고 테스트 시 불필요하므로 **지연 로딩**하며, PyTorch 모델이
스레드 안전하지 않으므로 전사(transcribe)는 락으로 직렬화한다.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Optional

import librosa
import numpy as np

logger = logging.getLogger("toneup")

_MODEL_NAME = os.environ.get("TONEUP_WHISPER_MODEL", "base")
_model: Any = None
_model_lock = threading.Lock()

# 한국어 대표 습관어/간투사. 단어 단위로 '정확히 일치'할 때만 센다.
HABIT_WORDS: list[str] = ["음", "어", "그", "저", "뭐", "이제", "약간", "그냥", "막", "좀"]


def get_model() -> Any:
    """Whisper 모델을 처음 필요할 때 한 번만 로드한다(스레드 안전)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                import whisper

                logger.info("Loading Whisper model: %s", _MODEL_NAME)
                _model = whisper.load_model(_MODEL_NAME)
    return _model


def _transcribe(audio: np.ndarray) -> dict[str, Any]:
    """16kHz float32 오디오 배열을 직렬화해 전사한다.

    파일 경로 대신 배열을 넘기면 Whisper 내부의 ffmpeg 재디코딩을 건너뛰어
    더 빠르고, ffmpeg PATH 의존도 없어진다. CPU에서는 fp16을 끈다.
    """
    import torch

    model = get_model()
    with _model_lock:
        return model.transcribe(audio, language="ko", fp16=torch.cuda.is_available())


def _count_habit_words(words: list[str]) -> list[dict[str, Any]]:
    """토큰 리스트에서 습관어가 '독립 단어'로 쓰인 횟수를 센다."""
    counts = {h: 0 for h in HABIT_WORDS}
    for w in words:
        token = re.sub(r"[^가-힣a-zA-Z0-9]", "", w)
        if token in counts:
            counts[token] += 1
    return [{"word": h, "count": counts[h]} for h in HABIT_WORDS]


def _analyze_pauses(audio_data: np.ndarray, sr: int, top_db: int = 30) -> tuple[int, float]:
    """무음 구간을 찾아 (휴지 횟수, 총 휴지 시간초)를 반환한다."""
    if sr == 0 or len(audio_data) == 0:
        return 0, 0.0

    intervals = librosa.effects.split(audio_data, top_db=top_db)
    if len(intervals) == 0:
        return 0, 0.0

    min_pause = int(0.3 * sr)  # 0.3초 이상만 의미있는 휴지로 카운트
    pause_count = 0
    pause_samples = 0
    prev_end = intervals[0][1]
    for start, end in intervals[1:]:
        gap = start - prev_end
        if gap >= min_pause:
            pause_count += 1
            pause_samples += gap
        prev_end = end

    return pause_count, round(pause_samples / sr, 2)


def _analyze_pitch(audio_data: np.ndarray, sr: int) -> dict[str, Any]:
    """음정(F0)을 추출해 평균/변화폭(반음)과 억양 풍부함 라벨을 만든다."""
    default = {"pitch_mean": 0.0, "pitch_range": 0.0, "pitch_label": "분석 불가"}
    if sr == 0 or len(audio_data) < sr // 2:
        return default
    try:
        f0, _, _ = librosa.pyin(audio_data, fmin=65, fmax=400, sr=sr)
    except Exception as e:  # pragma: no cover
        logger.warning("pitch analysis failed: %s", e)
        return default

    voiced = f0[~np.isnan(f0)]
    if len(voiced) < 5:
        return default

    pitch_mean = float(np.mean(voiced))
    p5, p95 = np.percentile(voiced, [5, 95])  # 이상치 영향 축소
    p5 = max(p5, 1e-6)
    pitch_range = float(12 * np.log2(p95 / p5)) if p95 > 0 else 0.0

    if pitch_range < 2.5:
        label = "단조로움"
    elif pitch_range <= 7:
        label = "적절한 억양"
    else:
        label = "풍부한 억양"

    return {
        "pitch_mean": round(pitch_mean, 1),
        "pitch_range": round(pitch_range, 2),
        "pitch_label": label,
    }


def _analyze_volume(audio_data: np.ndarray, sr: int) -> dict[str, Any]:
    """RMS 기반 음량(dBFS)과 음량 일관성(0~100)을 계산한다."""
    default = {"volume_db": -120.0, "volume_consistency": 0, "volume_label": "분석 불가"}
    if len(audio_data) == 0:
        return default

    rms = librosa.feature.rms(y=audio_data)[0]
    rms = rms[rms > 1e-5]  # 무음 프레임 제외
    if len(rms) == 0:
        return default

    mean_rms = float(np.mean(rms))
    volume_db = float(20 * np.log10(mean_rms + 1e-9))
    cv = float(np.std(rms) / (mean_rms + 1e-9))  # 변동계수(작을수록 일관)
    volume_consistency = int(max(0, min(100, round((1 - cv) * 100))))

    if volume_db < -35:
        label = "작음"
    elif volume_db <= -12:
        label = "적절"
    else:
        label = "큼"

    return {
        "volume_db": round(volume_db, 1),
        "volume_consistency": volume_consistency,
        "volume_label": label,
    }


def _analyze_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Whisper segment 타임스탬프로 문장(구간)별 말속도·명료도를 계산한다."""
    out: list[dict[str, Any]] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or 0.0)
        seg_dur = max(end - start, 1e-6)

        syllables = len(re.sub(r"[^가-힣]", "", text))
        if syllables == 0:
            syllables = len(text.replace(" ", ""))
        sps = round(syllables / seg_dur, 2)

        clarity: Optional[int] = None
        if seg.get("avg_logprob") is not None:
            clarity = int(round((1 + max(float(seg["avg_logprob"]), -1.0)) * 100))
            clarity = max(0, min(clarity, 100))

        out.append({
            "start": round(start, 1),
            "end": round(end, 1),
            "text": text,
            "sps": sps,
            "clarity": clarity,
        })
    return out


def _overall_score(
    pron_score: int,
    sps: float,
    total_habits: int,
    duration: float,
    pause_ratio: float,
    pitch_range: float,
) -> int:
    """지표들을 가중 합산한 종합 점수(0~100).

    발음 35% · 속도 20% · 억양 20% · 습관어 15% · 휴지 10%.
    """
    # 속도: 2.5~4.5 SPS가 이상적, 벗어날수록 감점
    if 2.5 <= sps <= 4.5:
        speed = 100.0
    else:
        dist = (2.5 - sps) if sps < 2.5 else (sps - 4.5)
        speed = max(0.0, 100.0 - dist * 45.0)

    # 습관어: 분당 사용 횟수 기반 감점
    hpm = (total_habits / (duration / 60)) if duration > 0 else 0.0
    habit = max(0.0, 100.0 - hpm * 12.0)

    # 휴지: 5~30%가 자연스러움
    if 5.0 <= pause_ratio <= 30.0:
        pause = 100.0
    elif pause_ratio < 5.0:
        pause = 70.0 + pause_ratio * 6.0  # 쉼이 너무 없으면 소폭 감점
    else:
        pause = max(0.0, 100.0 - (pause_ratio - 30.0) * 3.0)

    # 억양: 변화폭 2.5반음 이상이면 만점, 단조로울수록 감점
    pitch = 100.0 if pitch_range >= 2.5 else 40.0 + (pitch_range / 2.5) * 60.0

    score = 0.35 * pron_score + 0.2 * speed + 0.2 * pitch + 0.15 * habit + 0.1 * pause
    return int(round(max(0.0, min(100.0, score))))


def _shorten(text: str, limit: int = 24) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _analyze_emotion(
    pitch: dict[str, Any], volume: dict[str, Any], sps: float, pause_ratio: float
) -> dict[str, Any]:
    """음향 특징(음정 변화·음량·속도)으로 '발화 톤(에너지)'을 추정한다.

    실제 감정 인식이 아니라 운율 기반 휴리스틱이므로 라벨은 '추정'으로 다룬다.
    """
    pitch_range = pitch.get("pitch_range", 0.0)
    volume_db = volume.get("volume_db", -120.0)

    def _scale(v: float, lo: float, hi: float) -> float:
        if hi == lo:
            return 0.0
        return max(0.0, min(1.0, (v - lo) / (hi - lo)))

    vol_norm = _scale(volume_db, -40, -10)     # 음량
    pitch_norm = _scale(pitch_range, 0, 10)    # 억양 다양성
    tempo_norm = _scale(sps, 1.5, 5.0)         # 말속도
    energy = int(round((0.4 * vol_norm + 0.35 * pitch_norm + 0.25 * tempo_norm) * 100))
    energy = max(0, min(100, energy))

    if energy >= 68:
        label = "활기참"
    elif energy <= 35:
        label = "가라앉음"
    elif pitch_range < 2.5:
        label = "단조로움"
    elif sps > 4.7 and pause_ratio < 15:
        label = "다소 긴장됨"
    else:
        label = "안정적"

    return {"emotion_label": label, "energy": energy}


def analyze_audio(file_path: str) -> Optional[dict[str, Any]]:
    """WAV 파일을 분석해 결과 dict를 반환한다. 인식 실패 시 None."""
    try:
        audio_data, sr = librosa.load(file_path, sr=None)
        duration = len(audio_data) / sr if sr else 0.0
        if duration < 0.5:
            return None

        # Whisper는 16kHz float32 입력을 기대한다 (업로드 파이프라인은 이미 16kHz).
        if sr != 16000:
            audio16 = librosa.resample(audio_data, orig_sr=sr, target_sr=16000)
        else:
            audio16 = audio_data
        whisper_out = _transcribe(np.ascontiguousarray(audio16, dtype=np.float32))
        text = (whisper_out.get("text") or "").strip()
        words = text.split()
        word_count = len(words)
        if word_count == 0:
            return None

        # 말속도: 한국어는 SPS(음절/초)가 적합, WPM은 보조 지표
        syllables = sum(len(re.sub(r"[^가-힣]", "", w)) for w in words)
        if syllables == 0:
            syllables = sum(len(w) for w in words)
        sps = round((syllables / duration) if duration > 0 else 0.0, 2)
        wpm = int(word_count / (duration / 60)) if duration > 0 else 0

        if sps < 2.5:
            speed_label = "느린 편"
        elif sps <= 4.5:
            speed_label = "적절한 속도"
        else:
            speed_label = "빠른 편"

        # 발음 점수: Whisper segment 평균 logprob 기반 (0~100)
        avg_scores = [
            seg["avg_logprob"]
            for seg in whisper_out.get("segments", [])
            if "avg_logprob" in seg
        ]
        if avg_scores:
            avg_logprob = float(np.mean(avg_scores))
            pron_score = int(round((1 + max(avg_logprob, -1.0)) * 100))
            pron_score = max(0, min(pron_score, 100))
        else:
            pron_score = 0

        habits = _count_habit_words(words)
        total_habits = sum(h["count"] for h in habits)

        pause_count, pause_seconds = _analyze_pauses(audio_data, sr)
        pause_ratio = round((pause_seconds / duration) * 100, 1) if duration > 0 else 0.0

        pitch = _analyze_pitch(audio_data, sr)
        volume = _analyze_volume(audio_data, sr)
        emotion = _analyze_emotion(pitch, volume, sps, pause_ratio)

        seg_infos = _analyze_segments(whisper_out.get("segments", []))
        overall = _overall_score(
            pron_score, sps, total_habits, duration, pause_ratio,
            pitch.get("pitch_range", 0.0),
        )

        feedback = _build_feedback(
            speed_label, total_habits, duration, pron_score,
            pause_ratio, pause_count, pitch, volume,
        )

        # 문장별 분석에서 가장 개선이 필요한 문장을 짚어준다.
        if len(seg_infos) >= 2:
            scored = [s for s in seg_infos if s["clarity"] is not None]
            if scored:
                worst = min(scored, key=lambda s: s["clarity"])
                if worst["clarity"] < 65:
                    feedback.append(
                        f"가장 흐리게 들린 문장: \"{_shorten(worst['text'])}\" — 이 문장을 또렷하게 다시 읽어보세요."
                    )
            fastest = max(seg_infos, key=lambda s: s["sps"])
            if fastest["sps"] > 5.5:
                feedback.append(
                    f"가장 빨랐던 문장: \"{_shorten(fastest['text'])}\" — 이 부분에서 한 박자 쉬어가세요."
                )

        result: dict[str, Any] = {
            "text": text,
            "duration": round(duration, 2),
            "word_count": word_count,
            "syllables": syllables,
            "wpm": wpm,
            "sps": sps,
            "speed_label": speed_label,
            "pron_score": pron_score,
            "habits": habits,
            "total_habits": total_habits,
            "pause_count": pause_count,
            "pause_seconds": pause_seconds,
            "pause_ratio": pause_ratio,
            "segments": seg_infos,
            "overall_score": overall,
            "feedback": feedback,
        }
        result.update(pitch)
        result.update(volume)
        result.update(emotion)
        return result
    except Exception as e:
        logger.exception("analyze_audio failed: %s", e)
        return None


def _build_feedback(
    speed_label: str,
    total_habits: int,
    duration: float,
    pron_score: int,
    pause_ratio: float,
    pause_count: int,
    pitch: dict[str, Any],
    volume: dict[str, Any],
) -> list[str]:
    """지표를 바탕으로 규칙 기반 코칭 메시지를 생성한다."""
    feedback: list[str] = []

    if speed_label == "느린 편":
        feedback.append("말 속도가 조금 느립니다. 자연스럽게 템포를 올려보세요.")
    elif speed_label == "빠른 편":
        feedback.append("말 속도가 빠릅니다. 한 박자 여유를 두고 발화해보세요.")
    else:
        feedback.append("말 속도가 적절합니다!")

    habit_per_min = (total_habits / (duration / 60)) if duration > 0 else 0
    if habit_per_min > 6:
        feedback.append(f"습관어를 분당 약 {habit_per_min:.0f}회 사용했어요. 의식적으로 줄여보세요.")
    elif total_habits > 0:
        feedback.append("습관어 사용이 적당합니다.")
    else:
        feedback.append("습관어가 거의 없어 깔끔합니다!")

    if pron_score < 60:
        feedback.append("발음이 조금 부정확해요. 또렷하게 발음해보세요.")
    elif pron_score < 80:
        feedback.append("발음이 비교적 좋습니다.")
    else:
        feedback.append("발음이 매우 또렷합니다!")

    if pause_ratio > 35:
        feedback.append("말 사이 멈춤이 다소 깁니다. 흐름을 좀 더 이어보세요.")
    elif pause_count <= 1 and duration > 5:
        feedback.append("쉼 없이 이어 말하고 있어요. 적절한 호흡도 좋습니다.")

    if pitch["pitch_label"] == "단조로움":
        feedback.append("억양 변화가 적어 단조롭게 들릴 수 있어요. 강조할 부분에 음을 실어보세요.")
    elif pitch["pitch_label"] == "풍부한 억양":
        feedback.append("억양이 풍부해 전달력이 좋습니다!")

    if volume["volume_label"] == "작음":
        feedback.append("목소리가 작은 편이에요. 조금 더 또렷하고 크게 말해보세요.")
    elif volume["volume_consistency"] < 50:
        feedback.append("음량 기복이 큰 편이에요. 일정한 크기를 유지해보세요.")

    return feedback
