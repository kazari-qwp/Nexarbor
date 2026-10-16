"""Read a bundled initial checkpoint, then bind explicitly mounted modules."""
from datanet.core.application import Component
def text(r,value):return r.resource(value['component'],value['file']) if isinstance(value,dict) else value



class Plugin(Component):
    def install(self):self.on('session/root',self.root)
    def root(self,e):
        key='network_presets/'+str(self.r.config.get('rootNetwork'))
        manifest=self.r.catalog.get(key,{})
        resource=manifest.get('initialNetwork')
        if not resource:return
        if set(self.r.backend.network.nodes)=={'root'}:
            document=self.r.resource(key,resource,True)
            for path,source in manifest.get('initialFiles',{}).items():document['files'][path]=text(self.r,source)
            self.r.rpc('network_initialize',document=document)
        root=manifest['rootSession']
        self.r.rpc('bind_agent',target='root',session_id=e['session_id'],kind='root',manager_id=None,creator_node_id=None)
        e['view']=self.r.bind('root',e['session_id'],root.get('role'),self.r.resolve(root['toolboxes']),text(self.r,root.get('prompt','')))
        self.r.backend.modules.bind(self.r)
