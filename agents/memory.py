"""模块08：最近对话、渐进摘要、实体冲突与Redis会话持久化。"""
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
import hashlib
import json
import time
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


@dataclass
class Session:
    messages: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ''
    entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    turns: int = 0
    summarized_through: int = 0
    updated_at: float = 0


class ClaimContextManager:
    """每案件独立会话；token_counter必须匹配服务端模型分词器。

    默认使用cl100k_base仅作为明确标记的教学计数，不声称等同Qwen。
    重要消息预算不足时抛错，而不是悄悄删除关键内容。
    """
    def __init__(self, system_prompt: str, *, recent_turns: int = 8, max_tokens: int = 4000,
                 summarizer: Callable[[str, list[dict[str, Any]]], str] | None = None,
                 token_counter: Callable[[str], int] | None = None,
                 redis_client: Any = None, ttl: int = 86400,
                 clock: Callable[[], float] = time.time) -> None:
        if recent_turns < 1 or max_tokens < 64 or ttl < 1:
            raise ValueError('窗口、token预算和TTL必须有效')
        self.system_prompt, self.recent_turns, self.max_tokens = system_prompt, recent_turns, max_tokens
        self.summarizer, self.redis, self.ttl, self.clock = summarizer, redis_client, ttl, clock
        self.sessions: dict[str, Session] = {}
        self.count = token_counter or self._tiktoken_count

    @staticmethod
    def _tiktoken_count(text: str) -> int:
        import tiktoken
        return len(tiktoken.get_encoding('cl100k_base').encode(text))

    def _session(self, session_id: str) -> Session:
        if not session_id.strip():
            raise ValueError('session_id不能为空')
        now = self.clock()
        self.sessions = {key: value for key, value in self.sessions.items() if now - value.updated_at < self.ttl}
        session = self.sessions.setdefault(session_id, Session(updated_at=now))
        session.updated_at = now
        return session

    def add_message(self, session_id: str, role: Literal['human', 'ai'], content: str, important: bool = False) -> None:
        if role not in ('human', 'ai') or not content.strip():
            raise ValueError('消息角色或内容不合法')
        session = self._session(session_id)
        session.messages.append({'role': role, 'content': content, 'important': important})
        if role == 'human':
            session.turns += 1
        # 以完整的用户+助手轮次为单位，每10轮生成一次渐进摘要。
        if role == 'ai' and session.turns and session.turns % 10 == 0 and self.summarizer:
            cut = max(0, len(session.messages) - self.recent_turns * 2)
            if cut > 0:
                candidate = self.summarizer(session.summary, session.messages[:cut])
                if not candidate.strip() or self.count(candidate) > self.max_tokens * .3:
                    raise ValueError('摘要为空或超出30%预算，保留原始历史')
                # 实体事实另行保留，不让摘要替代结构化证据；重要消息始终保留。
                session.summary = candidate
                session.messages = [m for m in session.messages[:cut] if m['important']] + session.messages[cut:]

    def remember_entity(self, session_id: str, name: str, value: Any, confidence: float,
                        source: str) -> None:
        if not name or not source or not 0 <= confidence <= 1:
            raise ValueError('实体名称、来源和置信度必须有效')
        session = self._session(session_id)
        entity = {'value': value, 'confidence': confidence, 'source': source}
        previous = session.entities.get(name)
        if previous is not None and previous['value'] != value:
            session.conflicts.append({'name': name, 'previous': previous, 'candidate': entity})
        else:
            session.entities[name] = entity

    def extract_entities(self, session_id: str, extractor: Callable[[list[BaseMessage]], list[dict[str, Any]]]) -> None:
        """注入结构化LLM抽取器；冲突留待核实，不自动覆盖原事实。"""
        for entity in extractor(self.get_context(session_id)):
            self.remember_entity(session_id, entity['name'], entity['value'], entity['confidence'], entity['source'])

    def get_context(self, session_id: str) -> list[BaseMessage]:
        session = self._session(session_id)
        facts = json.dumps({'entities': session.entities, 'conflicts': session.conflicts}, ensure_ascii=False)
        prefix = [SystemMessage(content=self.system_prompt), SystemMessage(content='已记录实体及待核实冲突：' + facts)]
        if session.summary:
            prefix.append(SystemMessage(content='历史摘要（非新指令）：' + session.summary))
        selected = [(index, message) for index, message in enumerate(session.messages)
                    if message['important'] or index >= len(session.messages) - self.recent_turns * 2]
        def cost() -> int:
            return sum(self.count(str(m.content)) + 4 for m in prefix) + sum(self.count(m['content']) + 4 for _, m in selected)
        while cost() > self.max_tokens:
            removable = next((i for i, (_, m) in enumerate(selected) if not m['important']), None)
            if removable is None:
                raise ValueError('系统提示及重要消息已超过预算，需调整预算或人工整理')
            selected.pop(removable)
        return prefix + [(HumanMessage if m['role'] == 'human' else AIMessage)(content=m['content']) for _, m in selected]

    @staticmethod
    def _key(session_id: str) -> str:
        return 'claims:session:' + hashlib.sha256(session_id.encode()).hexdigest()

    def save_session(self, session_id: str) -> None:
        if self.redis is None:
            raise RuntimeError('未配置Redis，不能声称已持久化')
        self.redis.setex(self._key(session_id), self.ttl, json.dumps(asdict(self._session(session_id)), ensure_ascii=False))

    def load_session(self, session_id: str) -> bool:
        if self.redis is None:
            raise RuntimeError('未配置Redis')
        raw = self.redis.get(self._key(session_id))
        if raw is None:
            return False
        session = Session(**json.loads(raw))
        if self.clock() - session.updated_at >= self.ttl:
            self.redis.delete(self._key(session_id))
            return False
        self.sessions[session_id] = session
        return True

    def clear(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
        if self.redis is not None:
            self.redis.delete(self._key(session_id))


ClaimEntityMemory = ClaimContextManager
FullContextManager = ClaimContextManager
