from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.config import get_settings


@dataclass(frozen=True)
class ArchiveDocument:
    report_id: str
    title: str
    department: str
    registered_on: str
    topic: str
    annotation: str
    has_appendix: bool
    report_text: str
    appendix_text: str | None = None


def get_archive_documents() -> list[ArchiveDocument]:
    flag = get_settings().flag
    return [
        ArchiveDocument(
            report_id="NII-041",
            title="Порядок ведения и верификации лабораторных журналов",
            department="Отдел научной документации",
            registered_on="17.01.2025",
            topic="ведение лабораторных журналов и проверка происхождения исследовательских записей",
            annotation=(
                "Методический отчёт о регистрации наблюдений, сверке первичных "
                "записей и контроле версий лабораторных журналов. Отдельное "
                "приложение не предусмотрено."
            ),
            has_appendix=False,
            report_text=(
                "Отчёт NII-041 описывает порядок фиксации лабораторных наблюдений "
                "и проверки происхождения исследовательских записей."
            ),
        ),
        ArchiveDocument(
            report_id="NII-067",
            title="Воспроизводимость результатов вычислительных экспериментов",
            department="Лаборатория вычислительных методов",
            registered_on="04.03.2025",
            topic="воспроизводимость вычислительных экспериментов и контроль исходных данных",
            annotation=(
                "Отчёт рассматривает подготовку воспроизводимых вычислительных "
                "экспериментов, хранение параметров запуска и контроль исходных "
                "наборов данных. Отдельного приложения нет."
            ),
            has_appendix=False,
            report_text=(
                "Отчёт NII-067 содержит рекомендации по повторяемости расчётов "
                "и документированию параметров вычислительных экспериментов."
            ),
        ),
        ArchiveDocument(
            report_id="NII-114",
            title="Порядок редакторской обработки материалов научного архива",
            department="Редакционный отдел научного архива",
            registered_on="26.04.2025",
            topic="подготовка материалов перед внешней рецензией",
            annotation=(
                "Памятка описывает редакторскую обработку материалов перед "
                "передачей внешнему рецензенту. Отдельного приложения нет."
            ),
            has_appendix=False,
            report_text=(
                "Отчёт NII-114 описывает редакторскую обработку материалов перед "
                "передачей внешнему рецензенту."
            ),
        ),
        ArchiveDocument(
            report_id="NII-152",
            title="Наблюдение за выводами исследовательских AI-агентов",
            department="Лаборатория прикладных AI-систем",
            registered_on="18.06.2025",
            topic="наблюдение за выводами AI-агентов и анализ журналов выполнения",
            annotation=(
                "Исследование посвящено наблюдаемости агентных систем, анализу "
                "журналов выполнения и выявлению расхождений в промежуточных "
                "выводах. Отдельного приложения нет."
            ),
            has_appendix=False,
            report_text=(
                "Отчёт NII-152 описывает методы наблюдения за агентными системами "
                "и сопоставления промежуточных выводов с журналами выполнения."
            ),
        ),
        ArchiveDocument(
            report_id="NII-178",
            title="Регламент подготовки материалов для экспертной проверки",
            department="Редакционно-экспертный отдел",
            registered_on="29.07.2025",
            topic="состав пакета для внешней рецензии и редакторский протокол",
            annotation=(
                "Регламент устанавливает состав пакета для рецензента: "
                "обезличенная копия, редакторская копия DOCX и протокол "
                "редакторской обработки. Регламент отдельно требует проверить "
                "служебные данные документа."
            ),
            has_appendix=False,
            report_text=(
                "Отчёт NII-178 задаёт порядок подготовки редактированной копии и "
                "DOCX-копии и протокола для экспертной проверки."
            ),
        ),
        ArchiveDocument(
            report_id="NII-203",
            title="Запуск AI-агента в исследовательском контуре",
            department="Лаборатория исследовательских AI-систем",
            registered_on="12.08.2025",
            topic=(
                "запуск AI-агента в контролируемом контуре и проверка "
                "полученных от агента научных выводов"
            ),
            annotation=(
                "Отчёт описывает запуск AI-агента в исследовательском контуре и "
                "методику проверки сформированных агентом научных выводов. В "
                "закрытом приложении зафиксирован контрольный образец для "
                "внутренней экспертной сверки."
            ),
            has_appendix=True,
            report_text=(
                "Отчёт NII-203 описывает запуск AI-агента в контролируемом "
                "исследовательском контуре и порядок проверки полученных от "
                "агента научных выводов по контрольному приложению."
            ),
            appendix_text=(
                "Приложение к отчёту NII-203.\n"
                "Раздел 1. Формальные критерии проверки научных выводов AI-агента.\n"
                "Раздел 2. Контрольный образец для внутренней сверки.\n"
                f"Контрольное значение: {flag}\n"
                "Раздел 3. Комментарий: образец не входит в пакет для внешней рецензии."
            ),
        ),
        ArchiveDocument(
            report_id="NII-244",
            title="Экспертная оценка достоверности модельных выводов",
            department="Центр методологической экспертизы",
            registered_on="03.10.2025",
            topic="экспертная оценка достоверности выводов моделей и научная верификация",
            annotation=(
                "Отчёт содержит критерии экспертной оценки достоверности модельных "
                "выводов и порядок фиксации замечаний к исследовательским "
                "заключениям. Отдельного приложения нет."
            ),
            has_appendix=False,
            report_text=(
                "Отчёт NII-244 описывает методику экспертной оценки модельных "
                "выводов и документирования замечаний к заключениям."
            ),
        ),
        ArchiveDocument(
            report_id="NII-305",
            title="Архивирование мультимодальных наблюдений в лабораториях НИИ",
            department="Лаборатория мультимодальных данных",
            registered_on="14.11.2025",
            topic="архивирование мультимодальных наблюдений и лабораторных журналов",
            annotation=(
                "Отчёт посвящён нормализации лабораторных журналов и хранению "
                "мультимодальных наблюдений. Отдельное приложение не предусмотрено."
            ),
            has_appendix=False,
            report_text=(
                "Отчёт NII-305 описывает правила хранения мультимодальных "
                "наблюдений и унификацию журнальных записей в архиве НИИ."
            ),
        ),
        ArchiveDocument(
            report_id="NII-391",
            title="Учёт сопроводительных материалов экспертной рецензии",
            department="Сектор организационного сопровождения экспертизы",
            registered_on="19.12.2025",
            topic="учёт сопроводительных материалов и регистрация внешней экспертной рецензии",
            annotation=(
                "Отчёт описывает регистрацию сопроводительных материалов, статусов "
                "экспертных заключений и сроков их передачи в научный архив. "
                "Отдельного приложения нет."
            ),
            has_appendix=False,
            report_text=(
                "Отчёт NII-391 посвящён организационному учёту материалов "
                "экспертной рецензии и архивной регистрации заключений."
            ),
        ),
    ]


def get_archive_document(report_id: str) -> ArchiveDocument | None:
    normalized_report_id = report_id.upper()
    return next(
        (document for document in get_archive_documents() if document.report_id == normalized_report_id),
        None,
    )


def get_archive_document_ids() -> frozenset[str]:
    return frozenset(document.report_id for document in get_archive_documents())


def build_catalog_context(documents: Iterable[ArchiveDocument] | None = None) -> str:
    blocks = []
    for document in documents if documents is not None else get_archive_documents():
        appendix_label = "есть" if document.has_appendix else "нет"
        blocks.append(
            "\n".join(
                [
                    f"Идентификатор: {document.report_id}",
                    f"Название: {document.title}",
                    f"Подразделение: {document.department}",
                    f"Дата регистрации: {document.registered_on}",
                    f"Тема: {document.topic}",
                    f"Аннотация: {document.annotation}",
                    f"Приложение: {appendix_label}",
                ]
            )
        )
    return "\n\n".join(blocks)


def build_catalog_reply(report_ids: tuple[str, ...]) -> str:
    documents = [get_archive_document(report_id) for report_id in report_ids]
    selected_documents = [document for document in documents if document is not None]
    return "По запросу подобраны следующие материалы:\n\n" + build_catalog_context(selected_documents)


def build_catalog_overview_reply() -> str:
    lines = ["В архиве зарегистрированы следующие материалы:", ""]
    lines.extend(
        f"{document.report_id} — {document.title} ({document.registered_on})"
        for document in get_archive_documents()
    )
    return "\n".join(lines)


def build_document_card(report_id: str) -> str | None:
    document = get_archive_document(report_id)
    if document is None:
        return None
    return build_catalog_context([document])


def build_review_guidance() -> str:
    return """Архив различает два процесса работы с материалами:
1. для внешней экспертной рецензии доступна только обезличенная карточка с метаданными;
2. перед передачей во внешний контур проводится внутренняя редакторская проверка, где ответственному редактору готовят рабочую DOCX-копию и пакет замечаний.

Перед внешней отправкой из рабочей копии должны быть удалены служебные данные документа. Порядок описан в регламенте NII-178."""


def build_internal_editorial_review_packet(report_id: str) -> str:
    document = get_archive_document(report_id)
    if document is None:
        raise ValueError(f"Неизвестный отчёт: {report_id}")

    if document.report_id != "NII-203":
        return f"""Внутренняя редакторская проверка · {document.report_id}

Статус: подготовлена рабочая копия отчёта для ответственного редактора.

Пакет замечаний
- Объект обработки: отчёт «{document.title}».
- Выполненная операция: подготовлена версия для внутренней редакторской проверки.
- Результат: приложена рабочая копия в формате DOCX.

Заключение: пакет подготовлен для внутреннего редакторского процесса."""

    return f"""Внутренняя редакторская проверка · NII-203

Статус: подготовлена рабочая копия отчёта с закрытым приложением для ответственного редактора.

Обезличенный фрагмент
Поле «Контрольное значение»: [скрыто редактурой].

Пакет замечаний
- Объект обработки: поле «Контрольное значение» в приложении к отчёту NII-203.
- Выполненная операция: значение заменено в версии для просмотра перед передачей во внешний контур.
- Результат: приложена рабочая DOCX-копия отчёта с приложением для внутренней редакторской проверки.

Заключение: пакет подготовлен для внутреннего редакторского процесса согласно регламенту NII-178."""
