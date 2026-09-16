"""材料6.5.2异步回写：持久化Outbox、幂等键、重试及对账。

入队不代表付款成功。真实消费者必须把同一幂等键传给下游，
下游也必须去重，才能覆盖“业务成功但本地未确认”的崩溃窗口。
"""
from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any


class Outbox:
    """SQLite教学/单节点Outbox；生产可替换为组织内消息队列适配器。"""
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, claim_id TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL, lease_until REAL NOT NULL DEFAULT 0)')

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def publish(self, claim_id: str, action: str, payload: dict[str, Any],
                idempotency_key: str) -> dict[str, Any]:
        if not claim_id or not action or not idempotency_key or len(idempotency_key) > 128:
            raise ValueError('案件、动作及幂等键必须非空且长度有效')
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        digest = hashlib.sha256(json.dumps([claim_id, action, body]).encode()).hexdigest()
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO outbox(id,claim_id,action,payload,digest,status) VALUES(?,?,?,?,?,?)',
                       (idempotency_key, claim_id, action, body, digest, 'queued'))
            row = db.execute('SELECT digest,status FROM outbox WHERE id=?', (idempotency_key,)).fetchone()
            if row[0] != digest:
                raise ValueError('同一幂等键不能对应不同业务参数')
        return {'idempotency_key': idempotency_key, 'status': row[1], 'paid': False}

    def consume_one(self, handler: Callable[[str, dict[str, Any], str], None]) -> bool:
        """获取租约后调用可信消费者；异常重入队，下游按原键幂等处理。"""
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT id,action,payload FROM outbox WHERE status='queued' OR (status='processing' AND lease_until<?) ORDER BY rowid LIMIT 1", (now,)).fetchone()
            if not row:
                return False
            db.execute("UPDATE outbox SET status='processing',lease_until=? WHERE id=?", (now + 60, row[0]))
        try:
            handler(row[1], json.loads(row[2]), row[0])
        except Exception:
            with self.connect() as db:
                db.execute("UPDATE outbox SET status='queued',lease_until=0 WHERE id=?", (row[0],))
            raise
        with self.connect() as db:
            db.execute("UPDATE outbox SET status='delivered',lease_until=0 WHERE id=?", (row[0],))
        return True

    def reconcile(self, remote_delivered_ids: set[str]) -> dict[str, list[str]]:
        """比对下游已处理键与本地投递状态，不自动补偿或再次付款。"""
        with self.connect() as db:
            local = {row[0] for row in db.execute("SELECT id FROM outbox WHERE status='delivered'")}
        return {'missing_remote': sorted(local - remote_delivered_ids),
                'missing_local': sorted(remote_delivered_ids - local)}
