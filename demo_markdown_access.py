r"""数字 Markdown 节点的手动访问测试。

在项目根目录执行：E:\miniconda3\python.exe -B -X utf8 demo_markdown_access.py
数据文件保留在 demo_data/markdown_access，文件内只有一个数字。

所有节点 bias=-1，默认求和；起点使用输入强度，接收节点汇合后减 1。
主测试用频道 a、强度 2：
  N0(2) -> N1(1), N2(1), N3(1)
  N1 + N2 -> N4(1) -> N6(0) -> N11(-1，阻断)
  N3 -> N5(0) -> N7(-1，阻断)
N8、N9 被频道阻挡；N2 -> N10 的阈值 2 阻挡强度 1。
拓扑包含分支、汇合和跨频道连接，不包含环路。
"""

import json
from pathlib import Path

from app.network_saver import NetworkSaver
from domain.core import access
from domain.core import Link
from domain.core import MarkdownNode
from domain.core import Module
from domain.core import Network
from domain.core import NodeInfo


DIRECTORY = Path(__file__).resolve().parent / 'demo_data' / 'markdown_access'
EDGES = [
    ('N0', 'N1', 'a', 0),
    ('N0', 'N2', 'a', 0),
    ('N0', 'N3', 'a', 0),
    ('N0', 'N8', 'b', 0),
    ('N1', 'N4', 'a', 0),
    ('N2', 'N4', 'a', 0),
    ('N1', 'N9', 'b', 0),
    ('N2', 'N10', 'a', 2),
    ('N3', 'N5', 'a', 0),
    ('N4', 'N6', 'a', 0),
    ('N4', 'N9', 'b', 0),
    ('N5', 'N7', 'a', 0),
    ('N6', 'N11', 'a', 0),
    ('N8', 'N9', 'b', 0),
    ('N9', 'N11', 'a', 0),
    ('N7', 'N11', 'a', 0),
    ('N10', 'N11', 'a', 0),
]


class NumberReader(Module):
    @access(channels='a', strength=2)
    def m(self, node):
        return int(node.dataer.read().strip())

    @access(channels='b', strength=2)
    def read_b(self, node):
        return int(node.dataer.read().strip())

    @access(channels='a', strength=3)
    def read_stronger(self, node):
        return int(node.dataer.read().strip())


def build_network():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    nodes = {}
    for index in range(12):
        node_id = f'N{index}'
        path = DIRECTORY / f'{node_id}.md'
        path.write_text(str(index * 10), encoding='utf-8')
        node = MarkdownNode(NodeInfo(node_id, node_id), path, save_data=False)
        node.bias = -1
        nodes[node_id] = node
    for source, target, channel, threshold in EDGES:
        nodes[source].links.add(Link(target, channel, threshold=threshold))
    return Network(nodes.values()), nodes


def main():
    network, nodes = build_network()
    reader = NumberReader('number_reader')
    nodes['N0'].install(reader)

    print('拓扑（节点偏置均为 -1）：')
    for source, target, channel, threshold in EDGES:
        print(f'  {source} --{channel}, threshold={threshold}--> {target}')

    # 主测试：直接调用用户要求的 m()，没有手动遍历或伪造读取结果。
    expected = {'N0': 0, 'N1': 10, 'N2': 20, 'N3': 30, 'N4': 40, 'N5': 50, 'N6': 60}
    result = reader.m()
    print('\na / strength=2:', json.dumps(result, ensure_ascii=False))
    assert result == expected, (result, expected)
    assert {'N7', 'N8', 'N9', 'N10', 'N11'}.isdisjoint(result)
    print('PASS：远端真实文件读取成功；负强度、频道和阈值分别阻止继续访问。')

    # 切换频道和提高强度，证明被挡住的节点确实存在且可以读取。
    result_b = reader.read_b()
    print('b / strength=2:', json.dumps(result_b, ensure_ascii=False))
    assert result_b == {'N0': 0, 'N8': 80, 'N9': 90}, result_b
    stronger = reader.read_stronger()
    print('a / strength=3:', json.dumps(stronger, ensure_ascii=False))
    assert set(stronger) == set(expected) | {'N7', 'N10', 'N11'}, stronger
    assert stronger['N7'] == 70 and stronger['N10'] == 100 and stronger['N11'] == 110

    # 对照：相同频道、相同输入强度，移除衰减后能够访问更远的节点。
    try:
        for node in network:
            node.bias = 0
        no_decay = reader.m()
        assert {'N7', 'N10', 'N11'} <= no_decay.keys(), no_decay
        print('a / strength=2 / bias=0:', json.dumps(no_decay, ensure_ascii=False))
    finally:
        for node in network:
            node.bias = -1

    # 外部修改远端文件，下一次调用立即读到新数字，最后恢复演示文件。
    remote_path = DIRECTORY / 'N4.md'
    try:
        remote_path.write_text('404', encoding='utf-8')
        assert reader.m() == {**expected, 'N4': 404}
        print('PASS：把远端 N4.md 改为 404 后，m() 立即返回 N4=404。')
    finally:
        remote_path.write_text('40', encoding='utf-8')

    # 保存并重新装配，验证偏置、连接和文件引用也能恢复。
    config = DIRECTORY / 'network.json'
    saver = NetworkSaver()
    saver.save(network, config)
    loaded = saver.load(config)
    reloaded_reader = NumberReader('number_reader')
    loaded.get('N0').install(reloaded_reader)
    assert all(node.bias == -1 for node in loaded)
    assert reloaded_reader.m() == expected
    print('PASS：保存、加载后，同样的模块调用得到相同结果。')
    print('全部手动测试通过。数据与配置：', DIRECTORY)


if __name__ == '__main__':
    main()
