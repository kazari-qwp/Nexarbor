from datanet.core.application import Component

class Plugin(Component):
    def install(self):
        self.actors = set()
        self.on('agent/bound', self.bound)

    def bound(self, event):
        actor = event['actor']
        self.r.host('component-extension', actor=actor, component=self.id, action='configure', arguments={})
        self.actors.add(actor)

    def close(self):
        for actor in self.actors:
            self.r.host('component-extension', actor=actor, component=self.id, action='dispose', arguments={})
