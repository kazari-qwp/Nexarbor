"""运行 python -m datanet.components.nodes.value_node.demo，演示网络读取单值节点。"""
from datanet.core.interface import Interface
import json
from dataclasses import asdict
from datanet.core.network import Network
from datanet.core.node import Node
from datanet.components.nodes.value_node import ValueNode

def main():
    root = Node('root', '项目入口', None)
    note = ValueNode(node_id='project_note', name='项目说明', data_kind='text', value='本项目使用模拟实验数据。')
    root.read_interfaces.append(Interface(note.node_id, threshold=0))
    network = Network()
    network.add_node(root)
    network.add_node(note)
    result = network.read('root', {'method': 'key', 'key': 'value'}, data_kind='text', strength=1)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
