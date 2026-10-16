from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Family(ActionModule):
    module_name='world.family';tools=TOOLS
    def apply(self,actor,name,args):
        b=self.backend;a=person(b,actor).state;partner=args['partner'];other=person(b,partner).state
        if actor==partner or other['place']!=a['place'] or a['spouse']!=partner or other['spouse']!=actor:raise ValueError('Only spouses present together may apply')
        if a['children'] or other['children']:raise ValueError('This demo allows one child per family')
        if any(set(v['parents'])=={actor,partner} for m in b.modules.find('world.family') for v in m.state['pregnancies'].values()):raise ValueError('Family plan already registered')
        carrier=actor if a.get('can_gestate') else partner if other.get('can_gestate') else None
        if not carrier:raise ValueError('No eligible gestational parent')
        if self.state['consents'].get(partner)!=dict(partner=actor,tick=tick(b)):
            self.state['consents'][actor]=dict(partner=partner,tick=tick(b));return dict(waiting_for=partner)
        import hashlib
        pid=hashlib.sha256(('\0'.join(sorted([actor,partner]))).encode()).hexdigest()[:12]
        due=tick(b)+self.config.get('duration',10)
        self.state['pregnancies'][pid]=dict(parents=sorted([actor,partner]),carrier=carrier,due_tick=due,child=None)
        self.state['consents'].pop(partner,None)
        other['last_result']=dict(ok=True,tool='plan_family',tick=tick(b),value=dict(expected_due=date(due)))
        return dict(registered=pid,expected_due=date(due))
def register(s):s.node_module('world.family',Family)
