"""Immutable signal values, independent of responders and applications."""
from dataclasses import dataclass,field,asdict
from copy import deepcopy
from uuid import uuid4
import math
from .interface import validate_strength
from .json_values import freeze,thaw,names

@dataclass(frozen=True)
class Signal:
    origin:str
    channels:tuple
    strength:float
    content:object=None
    kind:str='request'
    direction:str='write'
    signal_id:str=field(default_factory=lambda:uuid4().hex)
    parent_id:str|None=None
    sequence:int=0
    close_loop:bool=False
    failure_policy:str='stop'
    max_hops:int=32
    max_deliveries:int=1000
    timeout_seconds:float=180
    node_timeout_seconds:float=60

    def __post_init__(self):
        for key in ('origin','signal_id','kind'):
            if not isinstance(getattr(self,key),str) or not getattr(self,key):raise ValueError(key+' must be nonempty text')
        if self.parent_id is not None and (not isinstance(self.parent_id,str) or not self.parent_id):raise ValueError('Invalid parent_id')
        if type(self.sequence) is not int or self.sequence<0:raise ValueError('Invalid sequence')
        validate_strength(self.strength)
        object.__setattr__(self,'channels',names(self.channels,'channels',allow_empty=False))
        object.__setattr__(self,'content',freeze(self.content))
        if self.direction not in ('read','write'):raise ValueError('Invalid signal direction')
        if type(self.close_loop) is not bool:raise ValueError('close_loop must be boolean')
        if self.failure_policy not in ('stop','continue'):raise ValueError('Invalid failure policy')
        for key,minimum in [('max_hops',0),('max_deliveries',1)]:
            if type(getattr(self,key)) is not int or getattr(self,key)<minimum:raise ValueError('Invalid '+key)
        for key in ('timeout_seconds','node_timeout_seconds'):
            v=getattr(self,key)
            if type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=3600:raise ValueError('Invalid '+key)

    def to_dict(self):return thaw(asdict(self))

    @classmethod
    def from_dict(cls,value):return cls(**value)

@dataclass(frozen=True)
class SignalDelivery:
    node_id:str
    depth:int
    strength:float
    path:tuple
    parents:tuple

@dataclass(frozen=True)
class SignalContext:
    signal:Signal
    delivery:SignalDelivery
    network:object=field(repr=False,compare=False)

    @property
    def receipt_id(self):return self.signal.signal_id+':'+self.delivery.node_id


def restore_records(records):
    if not isinstance(records,dict):raise ValueError('signals must be an execution-record object')
    result=deepcopy(records)
    valid={'running','completed','partial','failed','timed_out','cancelled','interrupted','budget_exhausted'}
    for key,record in result.items():
        if not isinstance(record,dict) or record.get('status') not in valid:raise ValueError('Invalid signal record')
        signal=Signal.from_dict(record['signal'])
        if key!=signal.signal_id:raise ValueError('Signal record ID mismatch')
        freeze(record)
        if record['status']=='running':
            record['status']='interrupted'
            record['error']='Runtime stopped before all processing was recorded; explicit reconciliation required'
            for delivery in record.get('deliveries',[]):
                if delivery.get('status')=='processing':delivery['status']='interrupted'
    return result
