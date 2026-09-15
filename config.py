"""理赔 Agent 配置与模型工厂。"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

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


STOP_MARKER: Final[str] = "<END_CLAIM>"


def _chat(
    model: str,
    temperature: float = 0.0,
    *,
    top_p: float = 0.85,
    max_tokens: int = 512,
    stop: tuple[str, ...] = (STOP_MARKER,),
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    seed: int = 42,
    response_format: Literal["text", "json_object"] = "text",
) -> ChatOpenAI:
    """统一创建聊天模型，实例化不发起网络请求。"""
    return ChatOpenAI(
        model=model,
        base_url=OPENAI_BASE_URL,
        api_key=OPENAI_API_KEY,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        stop=list(stop),
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        # 固定种子仅尽力复现；服务端实现与模型版本也会影响结果。
        seed=seed,
        model_kwargs={"response_format": {"type": response_format}},
        timeout=120.0,
        max_retries=2,
    )


# 通用：报案理解、材料摘要与常规问答。
qwen_plus: Final[ChatOpenAI] = _chat(_env("QWEN_PLUS_MODEL", "qwen-plus"))
# 强推理：复杂责任分析、条款比对与多证据判断。
qwen_max: Final[ChatOpenAI] = _chat(_env("QWEN_MAX_MODEL", "qwen-max"))
# 轻量降级：简单分类和备用调用，自动切换由上层编排实现。
qwen_flash: Final[ChatOpenAI] = _chat(_env("QWEN_FLASH_MODEL", "qwen-flash"))


@dataclass(frozen=True)
class TaskProfile:
    """按任务选择模型档位和生成参数。"""

    tier: Literal["plus", "max", "flash"]
    temperature: float
    max_tokens: int
    top_p: float = 0.85
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    response_format: Literal["text", "json_object"] = "json_object"


# 判责/定损重准确，客服重自然，报告减少重复，风险分析扩大关注维度。
TASK_PROFILES: Final[dict[str, TaskProfile]] = {
    "intake": TaskProfile("plus", 0.2, 1000),
    "classification": TaskProfile("flash", 0.1, 300),
    "extraction": TaskProfile("plus", 0.1, 2000),
    "coverage": TaskProfile("max", 0.2, 2000),
    "assessment": TaskProfile("max", 0.2, 2000),
    "risk": TaskProfile("max", 0.2, 2000, presence_penalty=0.3),
    "decision": TaskProfile("max", 0.2, 2000),
    "report": TaskProfile("plus", 0.2, 3000, frequency_penalty=0.25),
    "human_review": TaskProfile("plus", 0.2, 2000),
    "customer_service": TaskProfile("plus", 0.6, 1000, top_p=0.9, response_format="text"),
    "status_query": TaskProfile("flash", 0.2, 300, response_format="text"),
    "fallback": TaskProfile("flash", 0.2, 500, response_format="text"),
}


def _task_model(profile: TaskProfile) -> ChatOpenAI:
    """将任务参数传入统一工厂，沿用环境变量指定的服务与模型。"""
    return _chat(
        _env(f"QWEN_{profile.tier.upper()}_MODEL", f"qwen-{profile.tier}"),
        temperature=profile.temperature,
        top_p=profile.top_p,
        max_tokens=profile.max_tokens,
        frequency_penalty=profile.frequency_penalty,
        presence_penalty=profile.presence_penalty,
        response_format=profile.response_format,
    )


MODEL_ROUTING: Final[dict[str, ChatOpenAI]] = {
    task: _task_model(profile) for task, profile in TASK_PROFILES.items()
}


def get_model(task: str) -> ChatOpenAI:
    """获取任务模型；未知任务显式报错，不自动降级判责。"""
    if task not in MODEL_ROUTING:
        raise ValueError(f"未知理赔任务：{task}")
    return MODEL_ROUTING[task]
