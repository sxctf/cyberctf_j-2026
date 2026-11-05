from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

from itsdangerous import BadData, URLSafeTimedSerializer

from app.config import get_settings
from app.services.archive_catalog import ArchiveDocument, get_archive_document


PACKAGE_URL_TTL_SECONDS = 10 * 60
TARGET_REPORT_ID = "NII-203"
REPORT_CONTENT_DIR = Path(__file__).resolve().parents[1] / "content" / "reports"
DOCX_MIMETYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class InvalidReviewPackage(ValueError):
    pass


def create_download_token(report_id: str) -> str:
    document = get_archive_document(report_id)
    if document is None:
        raise InvalidReviewPackage
    return _serializer().dumps({"report_id": document.report_id})


def read_download_token(token: str) -> str:
    try:
        payload = _serializer().loads(token, max_age=PACKAGE_URL_TTL_SECONDS)
    except BadData as exc:
        raise InvalidReviewPackage from exc

    report_id = payload.get("report_id") if isinstance(payload, dict) else None
    if not isinstance(report_id, str) or get_archive_document(report_id) is None:
        raise InvalidReviewPackage
    return report_id.upper()


def build_redacted_docx(report_id: str) -> BytesIO:
    document = get_archive_document(report_id)
    if document is None:
        raise InvalidReviewPackage

    includes_sensitive_property = document.report_id == TARGET_REPORT_ID
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _content_types_xml(includes_sensitive_property))
        package.writestr("_rels/.rels", _root_relationships_xml(includes_sensitive_property))
        package.writestr("word/document.xml", _build_document_xml(document))
        if includes_sensitive_property:
            package.writestr("docProps/custom.xml", _custom_properties_xml(get_settings().flag))
    archive.seek(0)
    return archive


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().flag, salt="review-package-download")


def _content_types_xml(include_custom_properties: bool) -> str:
    custom_properties = (
        "\n  <Override PartName=\"/docProps/custom.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.custom-properties+xml\"/>"
        if include_custom_properties
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>{custom_properties}
</Types>"""


def _root_relationships_xml(include_custom_properties: bool) -> str:
    custom_properties = (
        "\n  <Relationship Id=\"rId2\" "
        "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties\" "
        "Target=\"docProps/custom.xml\"/>"
        if include_custom_properties
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>{custom_properties}
</Relationships>"""


def _custom_properties_xml(flag: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
    xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <property fmtid="{{D5CDD505-2E9C-101B-9397-08002B2CF9AE}}" pid="2" name="SourceControlId">
    <vt:lpwstr>{escape(flag)}</vt:lpwstr>
  </property>
</Properties>"""


def _build_document_xml(document: ArchiveDocument) -> str:
    title = f"Рабочая редакторская копия отчёта {document.report_id}"

    paragraphs = [
        _paragraph(title, bold=True, size="32"),
        _paragraph(f"Название: {document.title}", bold=True),
        _paragraph(f"Подразделение: {document.department}"),
        _paragraph(f"Дата регистрации: {document.registered_on}"),
        _paragraph("Статус: подготовлено для внутренней редакторской проверки."),
    ]
    paragraphs.extend(_markdown_body_to_paragraphs(_load_report_markdown(document.report_id)))
    paragraphs.append(
        _paragraph(
            "Копия предназначена для внутреннего редакторского процесса и не заменяет архивный оригинал."
        )
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
{"\n".join(paragraphs)}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>"""


def _load_report_markdown(report_id: str) -> str:
    content_path = REPORT_CONTENT_DIR / f"{report_id}.md"
    try:
        text = content_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidReviewPackage from exc
    if not text.strip():
        raise InvalidReviewPackage
    return text


def _markdown_body_to_paragraphs(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    first_section = next(
        (index for index, line in enumerate(lines) if re.match(r"^##\s+\d+\.\s+", line)),
        0,
    )
    paragraphs: list[str] = []
    for raw_line in lines[first_section:]:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            paragraphs.append(_paragraph(line[3:], bold=True, size="26"))
            continue
        if line.startswith("### "):
            paragraphs.append(_paragraph(line[4:], bold=True, size="24"))
            continue
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        if line.startswith("- "):
            line = f"— {line[2:]}"
        paragraphs.append(_paragraph(line))
    if not paragraphs:
        raise InvalidReviewPackage
    return paragraphs


def _paragraph(text: str, *, bold: bool = False, size: str | None = None) -> str:
    properties = []
    if bold:
        properties.append("<w:b/>")
    if size is not None:
        properties.append(f'<w:sz w:val="{size}"/>')
    run_properties = f"<w:rPr>{''.join(properties)}</w:rPr>" if properties else ""
    return f"    <w:p><w:r>{run_properties}<w:t>{escape(text)}</w:t></w:r></w:p>"
