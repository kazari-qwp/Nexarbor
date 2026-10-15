from datanet.core.application import Component

class Plugin(Component):
    def install(self):
        self.actors=set()
        self.on('agent/bound',self.bound)
        self.on('tool/native-before',self.enter)

    def bound(self,e):
        actor=e['actor']
        if 'command_execution' not in self.r.state(actor)['grant']['expanded']:
            return
        policy={**self.manifest['commandPolicy'],**self.r.config.get('commandPolicy',{})}
        self.r.host('component-extension',actor=actor,component=self.id,action='configure',arguments=policy)
        self.actors.add(actor)

    def enter(self,e):
        if e['actor'] in self.actors and e['name'] in ('pwsh','bash','job_list','job_output','job_kill'):
            self.r.load(e['actor'],'toolbox:command_execution',self.r.resource(self.id,'AGENTS.md'))

    def close(self):
        for actor in self.actors:
            self.r.host('component-extension',actor=actor,component=self.id,action='dispose',arguments={})
