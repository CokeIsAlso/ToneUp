"""분석 결과를 PDF 리포트로 생성하는 서비스 (reportlab, 한글 폰트 사용)."""
from __future__ import annotations

import io
import logging
import os
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger("toneup")

# 한글 폰트 등록 (Windows 기본 맑은 고딕, 없으면 환경변수/대체 경로)
_FONT_NAME = "Korean"
_FONT_CANDIDATES = [
    os.environ.get("TONEUP_PDF_FONT", ""),
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\gulim.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]

_font_ready = False
for _path in _FONT_CANDIDATES:
    if _path and os.path.exists(_path):
        try:
            pdfmetrics.registerFont(TTFont(_FONT_NAME, _path))
            _font_ready = True
            break
        except Exception:  # pragma: no cover
            continue

if not _font_ready:  # pragma: no cover
    logger.warning("한글 폰트를 찾지 못해 Helvetica로 대체합니다(한글 깨질 수 있음).")
    _FONT_NAME = "Helvetica"


def _styles() -> tuple[ParagraphStyle, ParagraphStyle, ParagraphStyle, ParagraphStyle]:
    base = getSampleStyleSheet()
    title = ParagraphStyle("kTitle", parent=base["Title"], fontName=_FONT_NAME, fontSize=22, spaceAfter=6)
    h = ParagraphStyle("kH", parent=base["Heading2"], fontName=_FONT_NAME, fontSize=13, spaceBefore=12, spaceAfter=6)
    body = ParagraphStyle("kBody", parent=base["BodyText"], fontName=_FONT_NAME, fontSize=10.5, leading=16)
    small = ParagraphStyle("kSmall", parent=base["BodyText"], fontName=_FONT_NAME, fontSize=9, textColor=colors.grey)
    return title, h, body, small


def build_report_pdf(record: dict[str, Any]) -> io.BytesIO:
    """record dict를 받아 PDF 바이트(BytesIO)를 반환한다."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="ToneUp Report",
    )
    title, h, body, small = _styles()
    story: list[Any] = []

    story.append(Paragraph("ToneUp 발화 분석 리포트", title))
    story.append(Paragraph(f"생성일시: {record.get('created_at', '')}", small))
    story.append(Spacer(1, 8))

    overall = record.get("overall_score")
    metrics = [
        ["항목", "값"],
        ["종합 점수", f"{overall if overall is not None else '--'} / 100"],
        ["발음 점수", f"{record.get('pron_score', '--')} / 100"],
        ["말 속도", f"{record.get('sps', '--')} 음절/초 ({record.get('speed_label', '')})"],
        ["WPM", str(record.get("wpm", "--"))],
        ["녹음 길이", f"{record.get('duration', '--')} 초"],
        ["단어 수", str(record.get("word_count", "--"))],
        ["습관어 합계", f"{record.get('total_habits', '--')} 회"],
        ["휴지", f"{record.get('pause_count', '--')}회 / {record.get('pause_ratio', '--')}%"],
        ["음정(억양)", f"{record.get('pitch_mean', '--')}Hz, 변화폭 {record.get('pitch_range', '--')}반음 ({record.get('pitch_label', '')})"],
        ["음량", f"{record.get('volume_db', '--')}dB ({record.get('volume_label', '')}), 일관성 {record.get('volume_consistency', '--')}점"],
        ["발화 톤(추정)", f"{record.get('emotion_label', '--')} (에너지 {record.get('energy', '--')}/100)"],
    ]
    table = Table(metrics, colWidths=[55 * mm, 100 * mm])
    table.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(table)

    story.append(Paragraph("인식 텍스트", h))
    story.append(Paragraph(record.get("text") or "(없음)", body))

    habits = [hh for hh in record.get("habits", []) if hh.get("count", 0) > 0]
    if habits:
        story.append(Paragraph("습관어 사용", h))
        story.append(Paragraph(", ".join(f"{hh['word']} ({hh['count']}회)" for hh in habits), body))

    story.append(Paragraph("코칭 피드백", h))
    for fb in record.get("feedback", []):
        story.append(Paragraph(f"• {fb}", body))

    if record.get("ai_coaching"):
        story.append(Paragraph("AI 코칭", h))
        story.append(Paragraph(record["ai_coaching"], body))

    if record.get("ai_improved"):
        story.append(Paragraph("AI 말투 개선 예시", h))
        story.append(Paragraph(record["ai_improved"], body))

    doc.build(story)
    buf.seek(0)
    return buf
