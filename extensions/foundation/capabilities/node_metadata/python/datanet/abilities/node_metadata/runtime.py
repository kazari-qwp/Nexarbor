"""Configure optional metadata sources; consumers use the core metadata API."""
from datanet.core.application import Component
from .services import register_provider


class Plugin(Component):
    def install(self):pass

    def register(self,space,provider,*,public=False):
        register_provider(self.r.backend,space,provider,public=public)

    def set(self,node_id,space,values):
        result=self.r.rpc('node_metadata_set',actor='root',target=node_id,namespace=space,values=values)
        self.r.emit('node/metadata-changed',node_id=node_id,namespace=space)
        return result
