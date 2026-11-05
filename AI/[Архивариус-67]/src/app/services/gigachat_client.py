from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time

from gigachat import GigaChat
from gigachat.models import Chat, Messages

from app.config import get_settings
from app.services.prompt_logger import log_prompt


class LLMServiceError(RuntimeError):
    """Raised when the upstream LLM cannot provide a usable response."""


@dataclass(frozen=True)
class GuardrailDecision:
    decision: str
    reason: str


@dataclass(frozen=True)
class RouteDecision:
    action: str
    report_ids: tuple[str, ...]
    reason: str


def _build_client() -> GigaChat:
    settings = get_settings()
    if not settings.gigachat_credentials:
        raise LLMServiceError("GigaChat credentials are not configured")

    return GigaChat(
        credentials=settings.gigachat_credentials,
        scope=settings.gigachat_scope,
        verify_ssl_certs=settings.gigachat_verify_ssl_certs,
        timeout=settings.gigachat_timeout,
    )


def _chat(system_prompt: str, user_message: str, request_id: str = "") -> str:
    settings = get_settings()
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with _build_client() as client:
                response = client.chat(
                    payload=Chat(
                        model=settings.gigachat_model,
                        messages=[
                            Messages(role="system", content=system_prompt),
                            Messages(role="user", content=user_message),
                        ],
                        profanity_check=False,
                    )
                )
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1)
                continue
            log_prompt(request_id, "LLM_ERROR", system_prompt, user_message, str(exc))
            raise LLMServiceError(str(exc)) from exc

        try:
            content = response.choices[0].message.content
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1)
                continue
            raise LLMServiceError("Unexpected GigaChat response shape") from exc

        if not isinstance(content, str) or not content.strip():
            last_error = LLMServiceError("Empty response from GigaChat")
            if attempt < 2:
                time.sleep(1)
                continue
            raise last_error
        content = content.strip()
        log_prompt(request_id, "LLM_OK", system_prompt, user_message, content)
        return content

    raise LLMServiceError(str(last_error or "Unknown GigaChat error"))


def generate_assistant_reply(system_prompt: str, user_message: str, request_id: str = "") -> str:
    if get_settings().llm_backend == "fixture":
        from app.services.llm_fixture import fixture_assistant_reply

        return fixture_assistant_reply(user_message)
    return _chat(system_prompt=system_prompt, user_message=user_message, request_id=request_id)


def generate_guardrail_decision(
    system_prompt: str,
    user_message: str,
    request_id: str = "",
    *,
    stage: str,
) -> GuardrailDecision:
    if get_settings().llm_backend == "fixture":
        from app.services.llm_fixture import fixture_guardrail_decision

        return fixture_guardrail_decision(stage, user_message)

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            raw = _chat(system_prompt=system_prompt, user_message=user_message, request_id=request_id)
            decision, reason = _extract_decision(raw)
            if decision not in {"pass", "block"}:
                raise LLMServiceError("Guardrail decision must be pass or block")
            if not reason:
                reason = "причина не указана моделью"
            return GuardrailDecision(decision=decision, reason=reason)
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1)
                continue
            if isinstance(exc, LLMServiceError):
                raise exc
            raise LLMServiceError(str(exc)) from exc

    raise LLMServiceError(str(last_error or "Unknown guardrail error"))


def generate_route_decision(
    system_prompt: str,
    user_message: str,
    request_id: str = "",
    *,
    allowed_report_ids: frozenset[str],
) -> RouteDecision:
    if get_settings().llm_backend == "fixture":
        from app.services.llm_fixture import fixture_route_decision

        return _validate_route_decision(fixture_route_decision(user_message), allowed_report_ids)

    raw = _chat(system_prompt=system_prompt, user_message=user_message, request_id=request_id)
    try:
        return _validate_route_decision(_parse_route_decision(raw), allowed_report_ids)
    except LLMServiceError as error:
        repaired_raw = _chat(
            system_prompt=system_prompt,
            user_message=(
                "Исправьте свой предыдущий ответ маршрутизатора. Исходный запрос:\n"
                f"{user_message}\n\nПредыдущий ответ:\n{raw}\n\n"
                f"Причина отклонения: {error}.\n"
                "Верните только JSON по заданной схеме, без пояснений."
            ),
            request_id=request_id,
        )
        return _validate_route_decision(_parse_route_decision(repaired_raw), allowed_report_ids)


def _parse_route_decision(raw: str) -> RouteDecision:
    payload = _extract_json_object(raw)
    action = str(payload.get("action", "")).strip().lower()
    raw_report_ids = payload.get("report_ids", [])
    if not isinstance(raw_report_ids, list) or not all(
        isinstance(report_id, str) for report_id in raw_report_ids
    ):
        raise LLMServiceError("Router report_ids must be an array of strings")
    report_ids = tuple(report_id.strip().upper() for report_id in raw_report_ids)
    reason = str(payload.get("reason", "")).strip()
    if action not in {
        "catalog_overview",
        "catalog",
        "document_card",
        "review_guidance",
        "internal_editorial_review",
        "general",
    }:
        raise LLMServiceError("Router action is not allowed")
    return RouteDecision(action=action, report_ids=report_ids, reason=reason)


def _validate_route_decision(
    route: RouteDecision,
    allowed_report_ids: frozenset[str],
) -> RouteDecision:
    report_ids = route.report_ids
    if len(report_ids) != len(set(report_ids)):
        raise LLMServiceError("Router response contains duplicate report IDs")
    if not set(report_ids).issubset(allowed_report_ids):
        raise LLMServiceError("Router response contains an unknown report ID")
    if route.action == "catalog_overview" and not report_ids:
        return route
    if route.action == "catalog" and 1 <= len(report_ids) <= 3:
        return route
    if route.action == "document_card" and len(report_ids) == 1:
        return route
    if route.action == "internal_editorial_review" and len(report_ids) == 1:
        return route
    if route.action in {"review_guidance", "general"} and not report_ids:
        return route
    raise LLMServiceError("Router response has an invalid action and report ID combination")


def _extract_decision(raw: str) -> tuple[str, str]:
    text = raw.strip()
    line_decision = re.search(r"decision\s*[:=]\s*(pass|block)", text, re.IGNORECASE)
    line_reason = re.search(r"reason\s*[:=]\s*(.+)", text, re.IGNORECASE)
    if line_decision:
        decision = line_decision.group(1).strip().lower()
        reason = line_reason.group(1).strip() if line_reason else ""
        return decision, reason

    payload = _extract_json_object(text)
    decision = str(payload.get("decision", "")).strip().lower()
    reason = str(payload.get("reason", "")).strip()
    return decision, reason


def _extract_json_object(raw: str) -> dict[str, object]:
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    elif not text.startswith("{"):
        object_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if object_match:
            text = object_match.group(1)

    if text.startswith("{{") and text.endswith("}}"):
        text = text[1:-1]

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMServiceError(f"Failed to parse model JSON output: {exc}") from exc

    if not isinstance(payload, dict):
        raise LLMServiceError("Model payload must be an object")

    return payload
