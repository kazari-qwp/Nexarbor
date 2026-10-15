"""Persistent JSON barrier; caller supplies transaction locking and storage."""
from copy import deepcopy
import time

def begin(state,key,participants,timeout_seconds=180,now=None):
    if state.get('active'):
        if state['key']!=key:raise ValueError('Another round is active')
        return deepcopy(state)
    members=list(participants)
    if not members or len(members)!=len(set(members)):raise ValueError('Unique participants required')
    if not 0<timeout_seconds<=3600:raise ValueError('Invalid round timeout')
    now=time.time() if now is None else now
    state.clear();state.update(active=True,key=key,participants=members,submitted={},started_at=now,deadline=now+timeout_seconds)
    return deepcopy(state)

def submit(state,participant,payload,now=None):
    if not state.get('active') or participant not in state['participants']:raise ValueError('Not an active participant')
    old=state['submitted'].get(participant)
    if old:
        if old['status']=='submitted' and old['payload']==payload:return deepcopy(old)
        raise ValueError('Already submitted')
    if (time.time() if now is None else now)>=state['deadline']:raise TimeoutError('Round deadline exceeded')
    result=dict(status='submitted',payload=deepcopy(payload));state['submitted'][participant]=result
    return deepcopy(result)

def abandon(state,participant,reason):
    if not state.get('active') or participant not in state['participants']:raise ValueError('Not an active participant')
    state['submitted'].setdefault(participant,dict(status='unavailable',payload=None,reason=str(reason)[:500]))

def pending(state):return [p for p in state.get('participants',[]) if p not in state.get('submitted',{})]

def expire(state,now=None):
    if state.get('active') and (time.time() if now is None else now)>=state['deadline']:
        for p in pending(state):abandon(state,p,'round_timeout')
    return pending(state)

def finish(state):
    if not state.get('active') or pending(state):raise ValueError('Round still has pending participants')
    state['active']=False
    return deepcopy(state['submitted'])
