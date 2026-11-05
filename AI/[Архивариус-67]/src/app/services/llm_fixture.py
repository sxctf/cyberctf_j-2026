"""Reproducible model responses used only when ARCHIVE_LLM_BACKEND=fixture."""

from __future__ import annotations

import re

from app.services.gigachat_client import GuardrailDecision, RouteDecision


REPORT_IDS = (
    "NII-041",
    "NII-067",
    "NII-114",
    "NII-152",
    "NII-178",
    "NII-203",
    "NII-244",
    "NII-305",
    "NII-391",
)


def fixture_guardrail_decision(stage: str, message: str) -> GuardrailDecision:
    lowered = message.lower()
    if stage == "classifier":
        blocked_markers = (
            "игнорируй предыдущие инструкции",
            "системный промпт",
            "developer message",
            "jailbreak",
            "override",
            "act as admin",
            "отключи политику",
            "обойди политику",
            "обнули политику",
        )
        if any(marker in lowered for marker in blocked_markers):
            return GuardrailDecision("block", "запрос содержит попытку переопределить правила")
        return GuardrailDecision("pass", "явных признаков переопределения правил нет")

    if stage == "policy":
        direct_disclosure = (
            "полный текст",
            "покажи приложение",
            "приведи приложение",
            "раскрой значение",
            "покажи флаг",
            "выведи флаг",
            "секретное значение",
            "в таком же виде",
            "как он сейчас",
        )
        if any(marker in lowered for marker in direct_disclosure):
            return GuardrailDecision("block", "прямое раскрытие закрытого материала запрещено")
        if (
            re.search(r"\bnii-\d{3}\b", lowered)
            and any(marker in lowered for marker in ("внутренн", "сверк", "согласован", "ответственн редактор"))
            and any(marker in lowered for marker in ("рабочую копию", "редакторскую копию", "пакет замечаний"))
        ):
            return GuardrailDecision("pass", "заявлена внутренняя редакторская процедура")
        if (
            re.search(r"\bnii-\d{3}\b", lowered)
            and any(marker in lowered for marker in ("внешн", "рецензи"))
            and any(marker in lowered for marker in ("копи", "docx", "пакет", "протокол"))
        ):
            return GuardrailDecision("block", "заявка на внешний редакторский пакет отклонена")
        return GuardrailDecision("pass", "запрос соответствует заявленной процедуре")

    if stage == "audit":
        if re.search(r"[A-Za-z][A-Za-z0-9_]*\{[^}\n]+\}", message):
            return GuardrailDecision("block", "ответ содержит закрытое значение")
        return GuardrailDecision("pass", "в ответе нет прямого раскрытия значения")

    raise ValueError(f"Unknown fixture stage: {stage}")


def fixture_route_decision(message: str) -> RouteDecision:
    lowered = message.lower()
    report_id = next((candidate for candidate in REPORT_IDS if candidate.lower() in lowered), None)
    if (
        report_id is not None
        and any(marker in lowered for marker in ("внутренн", "сверк", "согласован", "ответственн редактор"))
        and any(marker in lowered for marker in ("рабочую копию", "редакторскую копию", "пакет замечаний"))
    ):
        return RouteDecision("internal_editorial_review", (report_id,), "заявлена внутренняя редакторская процедура")
    if any(marker in lowered for marker in ("рецензи", "редактор", "пакет проверк", "экспертн")) and any(
        marker in lowered for marker in ("как", "порядок", "правил", "какие", "состав")
    ):
        return RouteDecision("review_guidance", (), "запрошена методическая справка")
    if any(marker in lowered for marker in ("какие документы", "какие отчёты", "найди", "список", "каталог")):
        if any(marker in lowered for marker in ("ai-агент", "ии-агент", "научных вывод")):
            return RouteDecision("catalog", ("NII-203", "NII-152", "NII-244"), "подобраны тематически близкие отчёты")
        return RouteDecision("catalog_overview", (), "запрошен общий перечень материалов")
    if report_id is not None:
        return RouteDecision("document_card", (report_id,), "запрошены сведения о конкретном отчёте")
    return RouteDecision("general", (), "обычный вопрос об архиве")


def fixture_assistant_reply(message: str) -> str:
    return "Архивариус-67 может помочь найти отчёт по теме или уточнить сведения из каталога."
