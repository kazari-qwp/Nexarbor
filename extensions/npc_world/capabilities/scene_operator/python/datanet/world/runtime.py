"""Harness-facing tool forwarding to explicitly mounted scene modules."""
from datanet.core.application import Component
from datanet.world.model import instance,residents

class Plugin(Component):
    def install(self):self.on("tool/before",self.guide)
    def guide(self,e):
        if e["actor"]=="root" and e["name"].startswith("world_"):self.r.load("root","scene:operator",self.r.resource("network_presets/small_town","AGENTS.md"))
    def operator(self,actor):
        if actor!='root':raise PermissionError('Only the operator may control the scene')
        return instance(self.r.backend,actor,'scene.operator')
    def tool_world_look(self,actor,p):return self.r.rpc('world_look',actor=actor)
    def tool_world_messages(self,actor,p):return self.r.rpc('world_messages',actor=actor)
    def tool_world_observe(self,actor,p):return self.operator(actor).observe(p.get('target'))
    def tool_world_run_npc(self,actor,p):
        if p['target'] not in residents(self.r.backend):raise ValueError('Unknown resident')
        return self.operator(actor).run([p['target']],min(120,max(1,p.get('timeout_ms',90000)/1000)))
    def tool_world_round(self,actor,p):
        if not self.r.config.get('worldAllowFullRun',True):raise PermissionError('This runtime permits only single-NPC tests')
        return self.operator(actor).run(list(residents(self.r.backend)),min(180,max(1,p.get('timeout_seconds',180))))
    def close(self):
        for module in self.r.backend.modules.find('scene.operator'):module.close()
