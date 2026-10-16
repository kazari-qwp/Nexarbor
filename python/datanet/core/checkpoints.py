"""Incremental state journal, periodic snapshots and executor-neutral recovery points."""
import json,sqlite3
from copy import deepcopy
from threading import RLock
from uuid import uuid4
from filelock import FileLock
from .state_journal import canonical,checksum,diff,apply

class Checkpoints:
    def __init__(self,directory,snapshot_interval=100):
        if type(snapshot_interval) is not int or snapshot_interval<1:raise ValueError('Snapshot interval must be a positive integer')
        self.mutex=RLock();self.interval=snapshot_interval;self.lock=FileLock(str(directory/'runtime.lock'));self.lock.acquire(timeout=0)
        try:
            self.db=sqlite3.connect(directory/'checkpoints.sqlite3',check_same_thread=False)
            self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
            tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'checkpoints' in tables and 'journal_meta' not in tables:raise ValueError('Legacy checkpoint database is not supported; use an isolated new workspace')
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS journal_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS commits(id INTEGER PRIMARY KEY AUTOINCREMENT,parent_hash TEXT NOT NULL,state_hash TEXT NOT NULL,delta TEXT NOT NULL,operation_id TEXT);
                CREATE TABLE IF NOT EXISTS checkpoints(id INTEGER PRIMARY KEY,document TEXT NOT NULL,state_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pending(id TEXT PRIMARY KEY,method TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS recovery_points(id TEXT PRIMARY KEY,commit_id INTEGER NOT NULL,kind TEXT NOT NULL,contexts TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            """)
            version=self.db.execute("SELECT value FROM journal_meta WHERE key='version'").fetchone()
            if version and version[0]!='2':raise ValueError('Unsupported journal version')
            with self.db:self.db.execute("INSERT OR IGNORE INTO journal_meta VALUES ('version','2')")
            row=self.db.execute('SELECT id,state_hash FROM commits ORDER BY id DESC LIMIT 1').fetchone()
            self.head=row[0] if row else 0;self.head_hash=row[1] if row else '';self.document=self.read(self.head) if self.head else None
        except BaseException:
            if hasattr(self,'db'):self.db.close()
            self.lock.release();raise
    def read(self,commit_id):
        with self.mutex:
            end=self.db.execute('SELECT state_hash FROM commits WHERE id=?',(commit_id,)).fetchone()
            if not end:raise KeyError('Unknown journal commit')
            snapshot=self.db.execute('SELECT id,document,state_hash FROM checkpoints WHERE id<=? ORDER BY id DESC LIMIT 1',(commit_id,)).fetchone()
            if not snapshot:raise ValueError('Required full snapshot is missing')
            state=json.loads(snapshot[1]);last=snapshot[0];value_hash=checksum(state)
            if value_hash!=snapshot[2]:raise ValueError('Snapshot checksum mismatch')
            for seq,parent,expected,delta in self.db.execute('SELECT id,parent_hash,state_hash,delta FROM commits WHERE id>? AND id<=? ORDER BY id',(last,commit_id)):
                if seq!=last+1 or parent!=value_hash:raise ValueError('Broken journal chain')
                state=apply(state,json.loads(delta));value_hash=checksum(state)
                if value_hash!=expected:raise ValueError('Delta checksum mismatch')
                last=seq
            if last!=commit_id or value_hash!=end[0]:raise ValueError('Recovery commit mismatch')
            return state
    def latest(self):
        with self.mutex:return deepcopy(self.document)
    def begin(self,operation_id,method):
        with self.mutex,self.db:self.db.execute('INSERT INTO pending VALUES (?,?)',(operation_id,method))
    def commit(self,document,operation_id=None,force_snapshot=False):
        canonical(document)
        with self.mutex:
            changes=diff(self.document,document);value_hash=checksum(document);seq=self.head
            with self.db:
                if changes:
                    cursor=self.db.execute('INSERT INTO commits(parent_hash,state_hash,delta,operation_id) VALUES (?,?,?,?)',(self.head_hash,value_hash,canonical(changes),operation_id));seq=cursor.lastrowid
                if seq and (not self.head or force_snapshot or (changes and seq%self.interval==0)):
                    self.db.execute('INSERT OR IGNORE INTO checkpoints VALUES (?,?,?)',(seq,canonical(document),value_hash))
                if operation_id:self.db.execute('DELETE FROM pending WHERE id=?',(operation_id,))
            self.head=seq;self.head_hash=value_hash;self.document=deepcopy(document)
            return seq
    def pending(self):
        with self.mutex:return [dict(id=r[0],method=r[1],status='uncertain') for r in self.db.execute('SELECT id,method FROM pending')]
    def reconcile(self,operation_id,reason):
        if not isinstance(reason,str) or not reason.strip():raise ValueError('Reconciliation needs an explicit reason')
        with self.mutex,self.db:
            if not self.db.execute('SELECT 1 FROM pending WHERE id=?',(operation_id,)).fetchone():raise KeyError(operation_id)
            self.db.execute('INSERT OR REPLACE INTO journal_meta VALUES (?,?)',('reconciled:'+operation_id,reason));self.db.execute('DELETE FROM pending WHERE id=?',(operation_id,))
    def mark(self,contexts,kind='incremental',expected_commit=None):
        if kind not in ('incremental','full'):raise ValueError('Invalid recovery point kind')
        if not isinstance(contexts,dict) or any(not isinstance(k,str) or not isinstance(v,dict) for k,v in contexts.items()):raise ValueError('Executor recovery cursors must be objects keyed by node ID')
        canonical(contexts)
        with self.mutex:
            if not self.head:raise ValueError('No committed state')
            if self.pending():raise RuntimeError('Uncertain operations must be reconciled before publishing a recovery point')
            if expected_commit is not None and expected_commit!=self.head:raise RuntimeError('Network changed during executor cursor capture')
            point=uuid4().hex
            with self.db:
                if kind=='full':self.db.execute('INSERT OR IGNORE INTO checkpoints VALUES (?,?,?)',(self.head,canonical(self.document),self.head_hash))
                self.db.execute('INSERT INTO recovery_points(id,commit_id,kind,contexts) VALUES (?,?,?,?)',(point,self.head,kind,canonical(contexts)))
            return self.point(point)
    def point(self,point_id):
        with self.mutex:
            row=self.db.execute('SELECT id,commit_id,kind,contexts,created_at FROM recovery_points WHERE id=?',(point_id,)).fetchone()
            if not row:raise KeyError('Unknown recovery point')
            return dict(id=row[0],commit_id=row[1],kind=row[2],contexts=json.loads(row[3]),created_at=row[4])
    def points(self):
        with self.mutex:return [self.point(r[0]) for r in self.db.execute('SELECT id FROM recovery_points ORDER BY rowid')]
    def stats(self):
        with self.mutex:return dict(commit_id=self.head,state_hash=self.head_hash,incremental_count=self.db.execute('SELECT COUNT(*) FROM commits').fetchone()[0],full_snapshot_count=self.db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0],recovery_point_count=self.db.execute('SELECT COUNT(*) FROM recovery_points').fetchone()[0],snapshot_interval=self.interval)
    def bundle(self,point_id):
        with self.mutex:
            point=self.point(point_id);document=self.read(point['commit_id'])
            return dict(version=1,point=point,document=document,checksum=checksum(dict(point=point,document=document)))
    def close(self):
        with self.mutex:self.db.close();self.lock.release()
