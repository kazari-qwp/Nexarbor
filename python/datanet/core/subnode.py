"""亚节点：普通模块容器与独立出边表，归属关系不占业务连接。"""
from .node import Node
class Subnode(Node):
    signal_type='subnode'
    def __init__(self,node_id,name,data_kind=None,*,parent_id=None,use_parent_links=False,share_links=False):
        super().__init__(node_id,name,None,divergence=0)
        if parent_id is not None and (not isinstance(parent_id,str) or not parent_id):raise ValueError('亚节点归属编号无效')
        if type(use_parent_links) is not bool or type(share_links) is not bool:raise ValueError('亚节点连接开关必须是布尔值')
        self.parent_id=parent_id;self.use_parent_links=use_parent_links;self.share_links=share_links
