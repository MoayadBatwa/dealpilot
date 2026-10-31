from typing import Any, Dict, List, Optional, Union
import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from .models import AuditEvent

class Database:
    """Each mutation and its audit event commit atomically; keys reject changed payloads."""
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS operations (key TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL);
            ''')

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def get(self, kind: str, id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as db:
            row = db.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind,id)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind: str) -> List[Dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT data FROM records WHERE kind=? ORDER BY id", (kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def audits(self) -> List[Dict[str, Any]]:
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT data FROM audit ORDER BY id")]

    def write(self, kind: str, id: str, data: Dict[str, Any], key: str, operation: str = "save", fail: bool = False) -> Dict[str, Any]:
        payload = json.dumps(data, sort_keys=True)
        digest = hashlib.sha256(f"{kind}:{id}:{operation}:{payload}".encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT digest,result FROM operations WHERE key=?", (key,)).fetchone()
            if prior:
                if prior[0] != digest:
                    raise ValueError("Idempotency key reused with different content")
                return json.loads(prior[1])
            if fail:
                raise RuntimeError("Simulated CRM outage: write rolled back")
            db.execute("INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind,id,payload))
            event = AuditEvent(id=key, operation=operation, record_id=id, idempotency_key=key, timestamp=datetime.now(timezone.utc).isoformat())
            db.execute("INSERT INTO audit(data) VALUES (?)", (event.model_dump_json(),))
            db.execute("INSERT INTO operations VALUES (?,?,?)", (key,digest,payload))
        return data
