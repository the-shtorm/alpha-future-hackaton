import json

from app.core.config import ROOT
from app.schemas.requests import Product, Profile, clean_text

LABELS = json.loads((ROOT / "config/text_labels.ru.json").read_text(encoding="utf-8"))


def sentence(text):
    text = clean_text(text)
    return text.rstrip(".?!… ") + "." if text else ""


def build_query(profile: Profile) -> str:
    p = profile
    sector = p.business.sector
    parts = [
        f"Бизнес занимается {LABELS['sector'][sector]}" if sector not in (None, "OTHER", "UNKNOWN") else "",
        f"Цель финансирования — {LABELS['purpose'][p.request.purpose]}",
        LABELS["usageModeQuery"][p.request.usageMode],
        LABELS["collateralReadyQuery"][p.security.collateralReady],
        LABELS["guarantorReadyQuery"][p.security.guarantorReady],
        f"Дополнительные обстоятельства: {p.request.description}" if p.request.description else "",
    ]
    return "query: " + " ".join(sentence(s) for s in parts if s)


def build_passage(product: Product) -> str:
    p = product
    parts = [
        f"Тип финансирования — {LABELS['productType'][p.type]}",
        "Назначение — " + ", ".join(LABELS["purpose"][s] for s in p.purposes),
        *(LABELS["usageModePassage"][s] for s in p.usageModes),
        f"Сценарий применения: {p.targetScenario}",
        "Специализация по отраслям: " + ", ".join(LABELS["sector"][s] for s in p.targetSectors)
        if p.targetSectors
        else "",
        f"Специализация: {p.specialization}" if p.specialization else "",
        LABELS["collateralRequirementPassage"][p.collateralRequirement],
        LABELS["guarantorRequirementPassage"][p.guarantorRequirement],
        p.securityNote or "",
    ]
    return "passage: " + " ".join(sentence(s) for s in parts if s)
