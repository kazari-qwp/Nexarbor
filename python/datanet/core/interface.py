"""An interface owns one target and validated, immutable metadata."""
from dataclasses import dataclass,field
import math
from .json_values import freeze,names

def validate_signal(value):
    if type(value) not in (int,float):raise ValueError('内部信号必须为有限数值')
    try:finite=math.isfinite(value)
    except OverflowError:finite=False
    if not finite:raise ValueError('内部信号必须为有限数值')
    return value

def validate_strength(value):
    validate_signal(value)
    if value<0:raise ValueError('访问强度必须为有限非负数')
    return value

@dataclass(frozen=True)
class InterfaceMetadata:
    visibility:str='public'
    threshold:int=0
    multiplier:float=1
    channels:tuple=()
    attributes:dict=field(default_factory=dict)

    def __post_init__(self):
        if self.visibility not in ('public','private'):raise ValueError('visibility 必须为 public 或 private')
        if type(self.threshold) is not int or self.threshold<0:raise ValueError('连接门槛必须为非负整数')
        validate_strength(self.multiplier)
        if not isinstance(self.attributes,dict):raise ValueError('attributes must be a JSON object')
        object.__setattr__(self,'channels',names(self.channels,'channels'))
        object.__setattr__(self,'attributes',freeze(self.attributes))

@dataclass(frozen=True)
class Interface:
    target_node_id:str
    metadata:InterfaceMetadata=field(default_factory=InterfaceMetadata)

    def __post_init__(self):
        if not isinstance(self.target_node_id,str) or not self.target_node_id:raise ValueError('目标编号必须为非空字符串')
        if isinstance(self.metadata,dict):object.__setattr__(self,'metadata',InterfaceMetadata(**self.metadata))
        if not isinstance(self.metadata,InterfaceMetadata):raise TypeError('metadata must be InterfaceMetadata or an object')

    def allows(self,*,origin_node_id,source_node_id,strength):
        validate_signal(strength)
        m=self.metadata
        return strength>=m.threshold and (m.visibility=='public' or origin_node_id==source_node_id)

    def carries(self,channels,*,strength):
        validate_signal(strength)
        m=self.metadata
        return m.visibility=='public' and strength>=m.threshold and bool(set(channels).intersection(m.channels))


def metadata_schema():
    """The same contract is used by the Python values and model-facing management tools."""
    return {
        'type':'object',
        'properties':{
            'visibility':{'type':'string','enum':['public','private'],'default':'public'},
            'threshold':{'type':'integer','minimum':0,'default':0},
            'multiplier':{'type':'number','minimum':0,'default':1},
            'channels':{'type':'array','items':{'type':'string','minLength':1},'uniqueItems':True,'default':[]},
            'attributes':{'type':'object'},
        },
        'additionalProperties':False,
    }
