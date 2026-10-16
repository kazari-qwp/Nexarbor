"""NPC metadata and privately linked knowledge sources for the independent matcher."""
from copy import deepcopy
import re
from datanet.core.interface import Interface
from datanet.core.metadata import lookup
from datanet.components.nodes.text_file_node.text_file_node import TextFileNode


def base_attributes(w,actor):
    a=w['actors'][actor]
    return dict(name=a['name'],initial_goal=a['goal'],background=a.get('background',''),role=a['role'],gender=a.get('gender','unspecified'),can_gestate=a.get('can_gestate',False),
                life_stage='child' if a['role']=='child' else 'adult',is_parent=bool(a['children']),
                pregnant=any(v['carrier']==actor and not v.get('child') for v in w['pregnancies'].values()))


def attributes(b,w,actor):return b.network.get_metadata(actor)


def matches(spec,values):
    for key,expected in spec['when'].items():
        try:actual=lookup(values,key)
        except (KeyError,IndexError):return False
        if not (actual in expected if isinstance(expected,list) else actual==expected):return False
    return True


def configure(b,w,profiles):
    catalog=[];seen=set()
    for entry in profiles:
        spec=deepcopy(entry);key=spec['id']
        if not re.fullmatch(r'[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*)*',key) or key in seen:raise ValueError('Invalid or duplicate knowledge profile ID')
        if not isinstance(spec['when'],dict) or spec['delivery'] not in ('instructions','query'):raise ValueError('Invalid profile condition or delivery')
        seen.add(key);node_id='world/knowledge/'+key
        node=b.network.nodes.get(node_id)
        if node is None:
            node=TextFileNode(node_id,spec['name'],'text',b.directory/'world'/'knowledge'/(key+'.md'))
            b.network.add_node(node)
        if not isinstance(node,TextFileNode):raise ValueError('Knowledge profile ID is occupied')
        node.name=spec['name'];node.expose=['read'];node.write('content',spec.pop('content'))
        spec['node_id']=node_id;catalog.append(spec)
    w['knowledge_catalog']=catalog
    sync(b,w)
    return dict(nodes=[p['node_id'] for p in catalog])


def context_id(actor):return actor+'/context'

def sync(b,w):
    for actor in w['actors']:
        n=b.network.nodes[actor];values=attributes(b,w,actor)
        n.read_interfaces=[e for e in n.read_interfaces if not e.metadata.attributes.get('resident_knowledge')]
        assembly=b.network.nodes[context_id(actor)]
        assembly.read_interfaces=[Interface('world/time',{'threshold':1,'visibility':'private'})]
        for spec in w.get('knowledge_catalog',[]):
            if matches(spec,values):
                n.read_interfaces.append(Interface(spec['node_id'],{'threshold':1,'visibility':'private','attributes':{'resident_knowledge':True}}))
                assembly.read_interfaces.append(Interface(spec['node_id'],{'threshold':1,'visibility':'private'}))


def linked(b,w,actor):
    strength=b.agents.get(actor,{}).get('maxStrength',2)
    ids={e.target_node_id for e in b.network.nodes[actor].read_interfaces
         if e.metadata.attributes.get('resident_knowledge') and e.allows(origin_node_id=actor,source_node_id=actor,strength=strength)
         and 'read' in b.network.nodes[e.target_node_id].expose}
    values=attributes(b,w,actor)
    return [spec for spec in w.get('knowledge_catalog',[]) if spec['node_id'] in ids and matches(spec,values)]


def references(b,w,actor):
    return [dict(node_id=p['node_id'],name=p['name'],delivery=p['delivery']) for p in linked(b,w,actor)]


def documents(b,w,actor):
    return [dict(id=p['node_id'],name=p['name'],when=p['when'],delivery=p['delivery'],
                 text=b.network.nodes[p['node_id']]._read_key('content').items[0]['content']) for p in linked(b,w,actor)]
