from datanet.core.application import Component

class Plugin(Component):
    def invoke(self,actor,name,args):return self.r.backend.modules.get(actor,'tools.assembly').invoke(name,args)
