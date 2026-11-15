import json
import sqlite3
import time
from pathlib import Path
from .models import AuditTask, now

class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = self.directory / 'paperguard.sqlite3'
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, updated TEXT, cancelled INTEGER DEFAULT 0, body TEXT);
            CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, retrieved REAL, body TEXT);
            """)

    def connect(self):
        return sqlite3.connect(self.db, timeout=30)

    def save(self, task):
        task.updated_at = now()
        with self.connect() as db:
            db.execute('INSERT INTO tasks(id,updated,body) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,body=excluded.body', (task.task_id,task.updated_at,task.model_dump_json()))

    def get(self, task_id):
        with self.connect() as db:
            row = db.execute('SELECT body FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        return AuditTask.model_validate_json(row[0])

    def list(self):
        with self.connect() as db:
            rows = db.execute('SELECT body FROM tasks ORDER BY updated DESC').fetchall()
        return [AuditTask.model_validate_json(r[0]) for r in rows]

    def cancel(self, task_id, value=True):
        with self.connect() as db:
            db.execute('UPDATE tasks SET cancelled=? WHERE id=?',(int(value),task_id))

    def cancelled(self, task_id):
        with self.connect() as db:
            row = db.execute('SELECT cancelled FROM tasks WHERE id=?',(task_id,)).fetchone()
        return bool(row and row[0])

    def cached(self, key, ttl):
        with self.connect() as db:
            row = db.execute('SELECT retrieved,body FROM cache WHERE key=?',(key,)).fetchone()
        return json.loads(row[1]) if row and time.time()-row[0] < ttl else None

    def cache(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,time.time(),json.dumps(value,ensure_ascii=False)))

    def clear_cache(self):
        with self.connect() as db:
            db.execute('DELETE FROM cache')

    def delete(self, task_id):
        with self.connect() as db:
            db.execute('DELETE FROM tasks WHERE id=?',(task_id,))
