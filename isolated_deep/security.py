"""Deep Agents 隔离环境使用的最小脱敏实现。"""

from collections.abc import Mapping
import re
from typing import Any


def mask_pii(value: Any) -> Any:
    """递归脱敏常见凭证与个人标识，避免依赖主项目运行时。"""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if re.search(
                r"api.?key|password|secret|authorization|身份证|银行卡|手机号|地址",
                str(key),
                re.I,
            )
            else mask_pii(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [mask_pii(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]+", "[密钥]", value)
        value = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", "[身份证]", value)
        value = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号]", value)
        value = re.sub(r"(?<!\d)\d{16,19}(?!\d)", "[银行卡]", value)
        return re.sub(
            r"(?:住址|家庭地址|详细地址)\s*[:：]\s*[^\n，。；;]+",
            "地址：[已脱敏]",
            value,
        )
    return value
