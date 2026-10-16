"""One metadata read path; optional providers cannot replace standard fields."""
from .json_values import freeze,thaw


class MetadataRegistry:
    def __init__(self):self.providers={}

    def register(self,owner,provider):
        if not isinstance(owner,str) or not owner or not callable(provider):raise ValueError('Metadata provider needs an owner and callable')
        self.providers[owner]=provider

    def unregister(self,owner):self.providers.pop(owner,None)

    def read(self,node):
        result=node.standard_metadata();extensions={}
        for provider in tuple(self.providers.values()):
            values=provider(node.node_id)
            if not isinstance(values,dict):raise TypeError('Metadata extension must return namespaced objects')
            for space,fields in values.items():
                if not isinstance(space,str) or not space or space=='core' or space in extensions or not isinstance(fields,dict):raise ValueError('Invalid or conflicting metadata namespace')
                extensions[space]=thaw(freeze(fields))
        if extensions:result['extensions']=extensions
        return result


def lookup(value,key):
    """Read a field name or JSON Pointer without executing user expressions."""
    if not isinstance(key,str):raise ValueError('Metadata field must be text')
    if not key.startswith('/'):return value[key]
    for raw in key[1:].split('/'):
        part=raw.replace('~1','/').replace('~0','~')
        if isinstance(value,list):
            if not part.isdecimal() or len(part)>1 and part[0]=='0':raise KeyError(part)
            value=value[int(part)]
        elif isinstance(value,dict):value=value[part]
        else:raise KeyError(part)
    return value
