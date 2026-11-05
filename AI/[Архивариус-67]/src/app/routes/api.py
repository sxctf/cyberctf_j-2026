from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, abort, jsonify, request, send_file, url_for

from app.config import get_settings
from app.services.agent import decide_response_route, respond_to_route
from app.services.gigachat_client import LLMServiceError
from app.services.guardrail import (
    audit_response,
    classify_message,
    policy_check,
)
from app.services.prompt_logger import log_prompt
from app.services.review_package import (
    DOCX_MIMETYPE,
    InvalidReviewPackage,
    build_redacted_docx,
    create_download_token,
    read_download_token,
)
from app.services.state_store import (
    next_request_id,
    reset_state,
    session_expired,
    session_remaining_seconds,
)


api_bp = Blueprint("api", __name__, url_prefix="/api")


def _pipeline(classifier: str, policy: str, audit: str) -> dict[str, str]:
    return {
        "classifier": classifier,
        "policy": policy,
        "audit": audit,
    }


@api_bp.post("/chat")
def post_chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "тело запроса должно быть JSON-объектом"}), 400

    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"error": "поле message обязательно"}), 400

    request_id = next_request_id()

    if session_expired():
        remaining = session_remaining_seconds()
        log_prompt(request_id, "SESSION_EXPIRED", "", message)
        return jsonify(
            {
                "reply": f"Время сессии истекло. Сессия жива 10 минут, осталось {remaining} сек.",
                "pipeline": _pipeline("block", "block", "block"),
                "meta": {"mode": "session_expired", "request_id": request_id},
            }
        )

    log_prompt(request_id, "USER_INPUT", "", message)

    executor = ThreadPoolExecutor(max_workers=2)
    classifier_future = executor.submit(classify_message, message, request_id)
    policy_future = executor.submit(policy_check, message, request_id)
    try:
        try:
            classifier = classifier_future.result()
        except LLMServiceError:
            return jsonify(
                {
                    "reply": "Контур классификации временно недоступен. Запрос отклонён в безопасном режиме.",
                    "pipeline": _pipeline("block", "idle", "idle"),
                    "meta": {"mode": "llm_error", "request_id": request_id},
                }
            )

        if classifier.decision == "block":
            return jsonify(
                {
                    "reply": f"Запрос остановлен классификатором: {classifier.reason}",
                    "pipeline": _pipeline("block", "idle", "idle"),
                    "meta": {"mode": "classifier_blocked", "request_id": request_id},
                }
            )

        try:
            policy = policy_future.result()
        except LLMServiceError:
            return jsonify(
                {
                    "reply": "Контур проверки политики временно недоступен. Запрос отклонён в безопасном режиме.",
                    "pipeline": _pipeline("pass", "block", "idle"),
                    "meta": {"mode": "llm_error", "request_id": request_id},
                }
            )

        if policy.decision == "block":
            return jsonify(
                {
                    "reply": f"Политика ответа отклонила запрос: {policy.reason}",
                    "pipeline": _pipeline("pass", "block", "idle"),
                    "meta": {"mode": "policy_blocked", "request_id": request_id},
                }
            )
    finally:
        executor.shutdown(wait=False)

    try:
        route = decide_response_route(message, request_id)
        result = respond_to_route(route, message, request_id)
    except LLMServiceError:
        return jsonify(
            {
                "reply": "Исследовательский ассистент временно недоступен. Попробуйте повторить запрос позже.",
                "pipeline": _pipeline("pass", "pass", "idle"),
                "meta": {"mode": "llm_error", "request_id": request_id},
            }
        )

    try:
        audit = audit_response(message, result.reply, request_id)
    except LLMServiceError:
        return jsonify(
            {
                "reply": "Контур финального аудита временно недоступен. Публикация ответа отклонена в безопасном режиме.",
                "pipeline": _pipeline("pass", "pass", "block"),
                "meta": {"mode": "llm_error", "request_id": request_id},
            }
        )

    if audit.decision == "block":
        return jsonify(
            {
                "reply": f"Аудит публикации отклонил ответ: {audit.reason}",
                "pipeline": _pipeline("pass", "pass", "block"),
                "meta": {"mode": "audit_blocked", "request_id": request_id},
            }
        )

    artifacts = []
    if result.review_document_id is not None:
        token = create_download_token(result.review_document_id)
        artifacts.append(
            {
                "label": f"Рабочая редакторская копия {result.review_document_id} (.docx)",
                "url": url_for("api.review_package_download", token=token),
            }
        )

    return jsonify(
        {
            "reply": result.reply,
            "artifacts": artifacts,
            "pipeline": _pipeline("pass", "pass", "pass"),
            "meta": {"mode": result.mode, "request_id": request_id},
        }
    )


@api_bp.get("/review-packages/<token>/download")
def review_package_download(token: str):
    try:
        report_id = read_download_token(token)
        document = build_redacted_docx(report_id)
    except InvalidReviewPackage:
        abort(404)

    return send_file(
        document,
        mimetype=DOCX_MIMETYPE,
        as_attachment=True,
        download_name=f"{report_id}_рабочая_копия.docx",
    )


@api_bp.post("/reset")
def post_reset():
    if not get_settings().enable_admin_routes:
        abort(404)
    state = reset_state()
    return jsonify(
        {
            "status": "reset",
            "request_count": state.request_count,
            "last_reset_at": state.last_reset_at,
        }
    )
