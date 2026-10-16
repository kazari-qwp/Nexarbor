"""Optional text presentation policy over the ordinary core text node."""
from datanet.core.text_node import TextFileNode as PlainTextNode

class TextFileNode(PlainTextNode):
    def __init__(self, node_id, name, data_kind, file_path, *, description='', delivery='plain', max_chars=None):
        if delivery not in ('plain','query'):raise ValueError('Invalid text delivery')
        super().__init__(node_id,name,data_kind,file_path,description=description,max_chars=max_chars)
        self.delivery=delivery
    def install_local_tools(self):
        from datanet.core.read_request import request_schema
        self.register_tool('read',self.read,description='读取本节点文本。',parameters={'type':'object','properties':{'request':request_schema()},'required':['request'],'additionalProperties':False},read_only=True)
        self.register_tool('get_schema',self.get_schema,description='查看文本节点结构。',parameters={'type':'object','properties':{},'additionalProperties':False},read_only=True)
    def get_schema(self):return {**super().get_schema(),'delivery':self.delivery}
