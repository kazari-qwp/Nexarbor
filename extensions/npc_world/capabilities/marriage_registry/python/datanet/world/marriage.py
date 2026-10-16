from datanet.world.model import *
from datanet.core.component_registry import resource_directory
import json
TOOLS=json.loads((resource_directory(__file__).parents[2]/"tools.json").read_text(encoding="utf-8"))

class Marriage(ActionModule):
    module_name='world.marriage';tools=TOOLS
    def apply(self,actor,name,args):
        b=self.backend;a=person(b,actor).state;partner=args['partner'];other=person(b,partner).state
        if actor==partner or other['role']=='child' or other['place']!=a['place']:raise ValueError('Choose another adult present at this place')
        if a['spouse'] or other['spouse']:raise ValueError('Already married')
        consent=self.state['consents'].get(partner)
        if consent!=dict(partner=actor,tick=tick(b)):
            self.state['consents'][actor]=dict(partner=partner,tick=tick(b));return dict(waiting_for=partner)
        a['spouse']=partner;other['spouse']=actor;self.state['consents'].pop(partner,None)
        self.state['registrations'].append(dict(partners=sorted([actor,partner]),tick=tick(b)))
        other['last_result']=dict(ok=True,tool='marry',tick=tick(b),value=dict(married=actor))
        return dict(married=partner)
def register(s):s.node_module('world.marriage',Marriage)
