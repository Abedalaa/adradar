"""Angle classification for ad text (see technical plan, section 3, feature 2).

Identical ad text is classified once and reused across every RawAd that
shares it (text_hash lookup) to keep API spend flat as more ads pile up.
With no ANTHROPIC_API_KEY configured, falls back to a keyword heuristic
so the rest of the pipeline stays testable offline.
"""

import hashlib

from sqlalchemy.orm import Session

from . import config
from .models import Classification, RawAd

ANGLES = ["discount", "testimonial", "problem_solution", "fomo", "comparison", "other"]

ANGLE_LABELS_AR = {
    "discount": "خصم",
    "testimonial": "شهادة عميل",
    "problem_solution": "حل مشكلة",
    "fomo": "خوف من فوات الفرصة",
    "comparison": "مقارنة",
    "other": "أخرى",
}

_MODEL = "claude-haiku-4-5-20251001"

_TOOL = {
    "name": "classify_ad_angle",
    "description": "Classify the marketing angle of an ad's text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "angle": {"type": "string", "enum": ANGLES},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["angle", "confidence"],
    },
}

_KEYWORDS = {
    "discount": ["خصم", "%", "عرض", "تخفيض"],
    "testimonial": ["جربت", "تجربتي", "رأيي", "استخدمت"],
    "fomo": ["قبل نفاذ", "كمية محدودة", "لفترة محدودة", "آخر فرصة"],
    "problem_solution": ["مشكلة", "الحل", "تعبان من", "بتعاني"],
}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _classify_heuristic(text: str) -> tuple[str, float]:
    for angle, keywords in _KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return angle, 0.6
    return "other", 0.3


def _classify_with_claude(text: str) -> tuple[str, float]:
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=_MODEL,
        max_tokens=200,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "classify_ad_angle"},
        messages=[{"role": "user", "content": f"Classify this ad's marketing angle:\n\n{text}"}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input["angle"], float(block.input["confidence"])
    return "other", 0.0


def classify_unclassified(session: Session) -> dict:
    use_claude = bool(config.ANTHROPIC_API_KEY)
    pending = (
        session.query(RawAd)
        .outerjoin(Classification)
        .filter(Classification.id.is_(None))
        .all()
    )

    classified, reused = 0, 0
    for ad in pending:
        text_hash = _text_hash(ad.raw_text)
        cached = session.query(Classification).filter_by(text_hash=text_hash).first()
        if cached:
            session.add(
                Classification(
                    raw_ad_id=ad.id,
                    angle=cached.angle,
                    confidence=cached.confidence,
                    text_hash=text_hash,
                )
            )
            reused += 1
            continue

        angle, confidence = (
            _classify_with_claude(ad.raw_text) if use_claude else _classify_heuristic(ad.raw_text)
        )
        session.add(
            Classification(raw_ad_id=ad.id, angle=angle, confidence=confidence, text_hash=text_hash)
        )
        classified += 1

    session.commit()
    return {"classified": classified, "reused_cached": reused, "mode": "claude" if use_claude else "heuristic"}
