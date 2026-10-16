"""Restore a committed core recovery point into a new directory, preserving its executor cursors."""
import json
from pathlib import Path
from .state_journal import checksum,canonical

def validate_bundle(bundle):
    if not isinstance(bundle,dict) or set(bundle)!={'version','point','document','checksum'} or bundle['version']!=1:raise ValueError('Invalid recovery bundle')
    if checksum(dict(point=bundle['point'],document=bundle['document']))!=bundle['checksum']:raise ValueError('Recovery bundle checksum mismatch')
    if not isinstance(bundle['point'],dict) or not isinstance(bundle['point'].get('contexts'),dict):raise ValueError('Recovery bundle is missing executor markers')
    agents=bundle['document'].get('agents',{})
    required={node for node,binding in agents.items() if binding.get('session_id')}
    if set(bundle['point']['contexts'])!=required:raise ValueError('Recovery cursors must cover exactly the bound Agents')
    return bundle

def restore_bundle(bundle,directory):
    validate_bundle(bundle);directory=Path(directory).resolve()
    if directory.exists() and any(directory.iterdir()):raise ValueError('Recovery requires a new or empty directory; live state is never overwritten')
    directory.mkdir(parents=True,exist_ok=True)
    from .backend import Backend
    backend=Backend(directory)
    try:
        backend.restore(bundle['document']);backend.store.commit(backend.snapshot(),force_snapshot=True)
        record=dict(point=bundle['point'],status='pending' if bundle['point']['contexts'] else 'complete')
        with backend.store.db:backend.store.db.execute('INSERT OR REPLACE INTO journal_meta VALUES (?,?)',('executor_restore',canonical(record)))
        return dict(directory=str(directory),commit_id=backend.store.head,executor_restore=record)
    finally:backend.close()

def required_contexts(store):
    row=store.db.execute("SELECT value FROM journal_meta WHERE key='executor_restore'").fetchone()
    if not row:return {}
    record=json.loads(row[0]);return record['point']['contexts'] if record['status']=='pending' else {}

def acknowledge_executors(backend,sessions):
    cursors=required_contexts(backend.store)
    if not cursors:
        row=backend.store.db.execute("SELECT value FROM journal_meta WHERE key='executor_restore'").fetchone()
        if row and json.loads(row[0]).get('sessions')==sessions:return dict(ready=True)
        raise ValueError('No executor restoration is pending')
    if not isinstance(sessions,dict) or set(sessions)!=set(cursors) or any(not isinstance(v,str) or not v for v in sessions.values()) or len(set(sessions.values()))!=len(sessions):raise ValueError('Restored session IDs must exactly cover pending Agents')
    for node,session in sessions.items():backend.agents[node]['session_id']=session
    backend.store.commit(backend.snapshot(),force_snapshot=True)
    row=backend.store.db.execute("SELECT value FROM journal_meta WHERE key='executor_restore'").fetchone();record=json.loads(row[0]);record['status']='complete';record['sessions']=sessions
    with backend.store.db:backend.store.db.execute('UPDATE journal_meta SET value=? WHERE key=?',(canonical(record),'executor_restore'))
    return dict(ready=True)
