"""经类型校验的环境配置；本地推理为默认，百炼必须显式选择。"""
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """密钥不写入代码，兼容已有.env但不隐式选择云服务。"""
    model_config = SettingsConfigDict(env_file=Path(__file__).parent / '.env', extra='ignore')
    app_env: Literal['development', 'test', 'production'] = 'development'
    model_provider: Literal['local', 'bailian'] = 'local'
    business_mode: Literal['real', 'demo'] = 'real'
    local_llm_base_url: str = 'http://127.0.0.1:8000/v1'
    local_llm_api_key: SecretStr = SecretStr('EMPTY')
    openai_base_url: str = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    openai_api_key: SecretStr = SecretStr('')
    local_fast_model: str = 'Qwen2.5-14B-Instruct'
    local_main_model: str = 'Qwen2.5-32B-Instruct'
    local_pro_model: str = 'Qwen2.5-72B-Instruct'
    local_vision_model: str = 'Qwen2.5-VL-7B-Instruct'
    qwen_plus_model: str = 'qwen-plus'
    qwen_max_model: str = 'qwen-max'
    qwen_flash_model: str = 'qwen-flash'
    embedding_base_url: str = 'http://127.0.0.1:8000/v1'
    embedding_model: str = 'bge-m3'
    embedding_api_key: SecretStr = SecretStr('EMPTY')
    milvus_uri: str = 'http://127.0.0.1:19530'
    redis_url: str = 'redis://127.0.0.1:6379/0'
    langfuse_enabled: bool = False
    langfuse_host: str = 'http://127.0.0.1:3000'
    langfuse_public_key: str = ''
    langfuse_secret_key: SecretStr = SecretStr('')

    @field_validator('local_llm_base_url', 'embedding_base_url', 'openai_base_url', 'langfuse_host')
    @classmethod
    def endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('服务URL必须为不含凭证、查询参数和片段的HTTP(S)地址')
        return value.rstrip('/')

    @model_validator(mode='after')
    def required_keys(self) -> 'Settings':
        if self.model_provider == 'bailian' and not self.openai_api_key.get_secret_value():
            raise ValueError('百炼模式需要配置OPENAI_API_KEY')
        if self.langfuse_enabled and (not self.langfuse_public_key or not self.langfuse_secret_key.get_secret_value()):
            raise ValueError('开启LangFuse需要LANGFUSE_PUBLIC_KEY和LANGFUSE_SECRET_KEY')
        return self

    @property
    def model_url(self) -> str:
        return self.local_llm_base_url if self.model_provider == 'local' else self.openai_base_url

    @property
    def model_key(self) -> SecretStr:
        return self.local_llm_api_key if self.model_provider == 'local' else self.openai_api_key

    def model_name(self, tier: str) -> str:
        local = {'flash': self.local_fast_model, 'plus': self.local_main_model,
                 'max': self.local_pro_model, 'vision': self.local_vision_model}
        cloud = {'flash': self.qwen_flash_model, 'plus': self.qwen_plus_model,
                 'max': self.qwen_max_model, 'vision': 'qwen-vl-plus'}
        return (local if self.model_provider == 'local' else cloud)[tier]
