"""理赔 Agent 配置与模型工厂。"""

import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


def _env(name: str, default: str) -> str:
    """读取非空环境变量，缺省时使用默认值。"""
    return os.getenv(name, "").strip() or default


OPENAI_BASE_URL: Final[str] = _env(
    "OPENAI_BASE_URL", "http://127.0.0.1:8000/v1"
).rstrip("/")
# EMPTY 是无鉴权本地服务的占位值，真实密钥从环境注入。
OPENAI_API_KEY: Final[SecretStr] = SecretStr(_env("OPENAI_API_KEY", "EMPTY"))


def _chat(model: str, temperature: float = 0.0) -> ChatOpenAI:
    """统一创建聊天模型，实例化不发起网络请求。"""
    return ChatOpenAI(
        model=model,
        base_url=OPENAI_BASE_URL,
        api_key=OPENAI_API_KEY,
        temperature=temperature,
        timeout=120.0,
        max_retries=2,
    )


# 通用：报案理解、材料摘要与常规问答。
qwen_plus: Final[ChatOpenAI] = _chat(_env("QWEN_PLUS_MODEL", "qwen-plus"))
# 强推理：复杂责任分析、条款比对与多证据判断。
qwen_max: Final[ChatOpenAI] = _chat(_env("QWEN_MAX_MODEL", "qwen-max"))
# 轻量降级：简单分类和备用调用，自动切换由上层编排实现。
qwen_flash: Final[ChatOpenAI] = _chat(_env("QWEN_FLASH_MODEL", "qwen-flash"))
