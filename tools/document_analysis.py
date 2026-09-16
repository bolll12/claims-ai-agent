"""附件格式校验、文本抽取和多模态单证识别。"""

import base64
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from docx import Document
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError
from pypdf import PdfReader

from agents.middleware_audit import mask_pii
from models.workbench import DocumentAnalysis


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_DOCUMENT_TEXT = 30_000
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}
IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class DocumentValidationError(ValueError):
    """附件格式、大小或内容不符合要求。"""


class DocumentModelOutputError(ValueError):
    """模型没有返回约定的结构化识别结果。"""


def _safe_name(name: str | None) -> str:
    """移除路径信息和控制字符，保留用户可辨识文件名。"""
    value = Path(name or "未命名附件").name
    value = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
    return (value or "未命名附件")[:255]


def _verify_signature(suffix: str, content: bytes) -> None:
    """校验常见二进制魔数，避免只信任浏览器声明的类型。"""
    signatures = {
        ".pdf": (b"%PDF-",),
        ".docx": (b"PK\x03\x04",),
        ".png": (b"\x89PNG\r\n\x1a\n",),
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".webp": (b"RIFF",),
    }
    if suffix in signatures and not any(content.startswith(item) for item in signatures[suffix]):
        raise DocumentValidationError("文件内容与扩展名不一致")
    if suffix == ".webp" and content[8:12] != b"WEBP":
        raise DocumentValidationError("文件内容与扩展名不一致")


def extract_document(name: str | None, content: bytes) -> tuple[str, str, str]:
    """返回安全文件名、格式和文本；图片文本由视觉模型识别。"""
    file_name = _safe_name(name)
    suffix = Path(file_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise DocumentValidationError("仅支持 PDF、DOCX、TXT、Markdown、PNG、JPEG 和 WebP")
    if not content:
        raise DocumentValidationError("附件内容为空")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise DocumentValidationError("单个附件不能超过 10MB")
    _verify_signature(suffix, content)

    if suffix == ".pdf":
        reader = PdfReader(BytesIO(content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:50])
    elif suffix == ".docx":
        document = Document(BytesIO(content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    elif suffix in {".txt", ".md"}:
        text = content.decode("utf-8-sig")
    else:
        return file_name, suffix, ""
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise DocumentValidationError("未提取到文本；扫描件请上传 PNG、JPEG 或 WebP 图片")
    return file_name, suffix, text[:MAX_DOCUMENT_TEXT]


def _message_text(message: Any) -> str:
    """兼容 OpenAI 文本块与普通字符串响应。"""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return str(content)


def _parse_result(raw: str, file_name: str) -> DocumentAnalysis:
    """严格解析模型 JSON，不用虚构字段修复失败结果。"""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    try:
        payload = json.loads(cleaned)
        payload["document_id"] = uuid4().hex
        payload["file_name"] = file_name
        return DocumentAnalysis.model_validate(payload)
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise DocumentModelOutputError("模型未返回有效的单证识别结构") from exc


async def analyze_document(name: str | None, content: bytes, *, text_model: Any, vision_model: Any) -> DocumentAnalysis:
    """根据附件类型调用文本或视觉模型，返回带置信度和警告的结果。"""
    file_name, suffix, text = extract_document(name, content)
    system = SystemMessage(content=(
        "你是保险理赔单证识别助手。只提取附件中明确出现的信息，不推测缺失字段。"
        "返回单个 JSON 对象，必须包含 document_type、summary、fields、confidence、warnings。"
        "fields 是字符串键值对象；confidence 是 0 到 1；模糊、遮挡或缺页写入 warnings。"
        "不要输出 Markdown。身份证、银行卡、手机号等敏感值在输出中只保留末四位。"
    ))
    if suffix in IMAGE_MIME:
        encoded = base64.b64encode(content).decode("ascii")
        human = HumanMessage(content=[
            {"type": "text", "text": f"识别这份理赔附件：{file_name}"},
            {"type": "image_url", "image_url": {"url": f"data:{IMAGE_MIME[suffix]};base64,{encoded}"}},
        ])
        response = await vision_model.ainvoke([system, human])
    else:
        human = HumanMessage(content=f"文件名：{file_name}\n\n附件文本：\n{mask_pii(text)}")
        response = await text_model.ainvoke([system, human])
    return _parse_result(_message_text(response), file_name)
