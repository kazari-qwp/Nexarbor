"""Crash-safe checkpoints and an explicit uncertain-operation journal."""
import json
import sqlite3
from filelock import FileLock

class Checkpoints:

    def __init__(self, directory):
        self.lock = FileLock(str(directory / 'runtime.lock'))
        self.lock.acquire(timeout=0)
        self.db = sqlite3.connect(directory / 'checkpoints.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('\n            CREATE TABLE IF NOT EXISTS checkpoints(id INTEGER PRIMARY KEY, document TEXT NOT NULL);\n            CREATE TABLE IF NOT EXISTS pending(id TEXT PRIMARY KEY, method TEXT NOT NULL);\n        ')

    def latest(self):
        row = self.db.execute('SELECT document FROM checkpoints ORDER BY id DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else None

    def begin(self, operation_id, method):
        with self.db:
            self.db.execute('INSERT INTO pending VALUES (?, ?)', (operation_id, method))

    def commit(self, document, operation_id=None):
        content = json.dumps(document, ensure_ascii=False, allow_nan=False)
        with self.db:
            self.db.execute('INSERT INTO checkpoints(document) VALUES (?)', (content,))
            if operation_id:
                self.db.execute('DELETE FROM pending WHERE id = ?', (operation_id,))
            self.db.execute('DELETE FROM checkpoints WHERE id NOT IN (SELECT id FROM checkpoints ORDER BY id DESC LIMIT 3)')

    def pending(self):
        return [{'id': row[0], 'method': row[1], 'status': 'uncertain'} for row in self.db.execute('SELECT id, method FROM pending')]

    def close(self):
        self.db.close()
        self.lock.release()
