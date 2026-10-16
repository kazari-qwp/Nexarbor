"""Remember current applicability, never whether a history document is loaded."""
from copy import deepcopy
from datanet.core.json_values import freeze


def get(b,p):return deepcopy(b.extension_state.get('prompt_matching',{}).get(p['actor'],{}).get(p['scope']))


def put(b,p):
    if p['actor'] not in b.agents:raise ValueError('Prompt metadata requires a bound Agent')
    freeze(p['value'])
    b.extension_state.setdefault('prompt_matching',{}).setdefault(p['actor'],{})[p['scope']]=deepcopy(p['value'])
    return dict(saved=True)


def register(s):
    s.rpc('prompt_matching_get',get,mutation=False)
    s.rpc('prompt_matching_put',put,mutation=True)
