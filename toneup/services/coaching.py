"""OpenAI API 기반 AI 코칭/말투 개선 서비스.

모드(자유·읽기·면접·발표)에 따라 다른 관점으로 코칭하고, 사용자의 발화를
다듬은 '개선 표현'을 함께 생성한다. ``OPENAI_API_KEY``가 없거나 호출이 실패하면
빈 결과를 반환하고 앱은 규칙 기반 피드백으로 폴백한다.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("toneup")

EMPTY: dict[str, Optional[str]] = {"coaching": None, "improved_text": None}


def _model_name() -> str:
    # 호출 시점에 읽어 .env 로드 순서에 의존하지 않는다.
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def _mode_instruction(mode: str, context: str) -> str:
    context = (context or "").strip()
    if mode == "reading":
        return (
            f"사용자가 다음 문장을 소리 내어 읽으려 했습니다: \"{context}\".\n"
            "발음의 또렷함과 목표 문장과의 일치도 관점에서 코칭하세요."
        )
    if mode == "interview":
        return (
            f"면접 질문: \"{context}\".\n"
            "면접관 관점에서 답변 내용의 충실성(두괄식·구체성)과 전달력(속도·군더더기·자신감)을 "
            "함께 평가하고, 더 좋은 답변 방향을 제시하세요."
        )
    if mode == "presentation":
        topic = context or "자유 주제"
        return (
            f"발표 상황/주제: \"{topic}\".\n"
            "청중 앞 발표 전달력(말속도, 휴지 활용, 자신감 있는 음량, 습관어 제거, 강조)을 중심으로 코칭하세요."
        )
    return "사용자의 말하기를 발음·속도·억양·습관어·휴지 관점에서 종합적으로 코칭하세요."


def _build_prompt(result: dict[str, Any], mode: str, context: str) -> str:
    habits = ", ".join(
        f"{h['word']}({h['count']}회)"
        for h in result.get("habits", [])
        if h.get("count", 0) > 0
    ) or "없음"

    return (
        f"{_mode_instruction(mode, context)}\n\n"
        f"[인식 텍스트]\n{result.get('text', '')}\n\n"
        "[분석 지표]\n"
        f"- 녹음 길이: {result.get('duration')}초\n"
        f"- 말속도: {result.get('sps')} 음절/초 ({result.get('speed_label')}), {result.get('wpm')} WPM\n"
        f"- 발음 점수: {result.get('pron_score')}/100\n"
        f"- 습관어: {habits}\n"
        f"- 휴지: {result.get('pause_count')}회, 전체의 {result.get('pause_ratio')}%\n"
        f"- 억양: 평균 {result.get('pitch_mean')}Hz, 변화폭 {result.get('pitch_range')}반음 ({result.get('pitch_label')})\n"
        f"- 음량: {result.get('volume_db')}dB ({result.get('volume_label')}), 일관성 {result.get('volume_consistency')}/100\n"
        f"- 발화 톤(추정): {result.get('emotion_label')} (에너지 {result.get('energy')}/100)\n\n"
        "아래 JSON 형식으로만, 한국어로, 마크다운 없이 응답하세요:\n"
        '{\n'
        '  "coaching": "3~4문장의 따뜻하고 구체적인 실천형 코칭",\n'
        '  "improved": "사용자 발화에서 습관어를 제거하고 더 또렷하고 자연스럽게 다듬은 문장 (발화가 없으면 빈 문자열)"\n'
        '}'
    )


def generate_ai_feedback(
    result: dict[str, Any], mode: str = "free", context: str = ""
) -> dict[str, Optional[str]]:
    """모드별 AI 코칭과 개선 표현을 한 번의 호출로 생성한다.

    반환: ``{"coaching": str|None, "improved_text": str|None}``
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return dict(EMPTY)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=_model_name(),
            messages=[
                {"role": "system", "content": "당신은 전문 한국어 스피치·면접·발표 코치입니다. 반드시 JSON으로만 응답합니다."},
                {"role": "user", "content": _build_prompt(result, mode, context)},
            ],
            temperature=0.7,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        coaching = (data.get("coaching") or "").strip() or None
        improved = (data.get("improved") or "").strip() or None
        return {"coaching": coaching, "improved_text": improved}
    except Exception as e:
        logger.warning("AI feedback failed, falling back: %s", e)
        return dict(EMPTY)


# 하위 호환용 (단순 코칭 문자열만 필요할 때)
def generate_ai_coaching(result: dict[str, Any]) -> Optional[str]:
    return generate_ai_feedback(result).get("coaching")
