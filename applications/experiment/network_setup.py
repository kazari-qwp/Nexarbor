"""实验项目的节点配置，存储实现由 datanet 提供。"""

from functools import partial
from pathlib import Path

from config import NETWORK_PATH
from datanet.serialization import load_network
from datanet.nodes.local_tools import attach_local_tools
from datanet.tool_access import attach_discovery_tools
from applications.experiment.tools.network_tools import analyze_project_via_network


def build_lab_network(db_path=None, records_path=None, *, config_path=NETWORK_PATH):
    """结构从配置加载；可覆盖数据路径以使用独立测试数据。"""
    network = load_network(config_path)
    root = network.nodes["root"]
    if db_path is not None:
        network.nodes["lab_rules"].db_path = Path(db_path).resolve()
    if records_path is not None:
        network.nodes["lab_records"].file_path = Path(records_path).resolve()
    for node in network.nodes.values():
        attach_local_tools(node)
    root.tools["analyze_project"] = partial(
        analyze_project_via_network, network=network,
        entry_node_id=root.node_id, scope="integrated",
    )
    root.register_tool("analyze_project", root.tools["analyze_project"],
        description="组合规则和记录计算项目合格率，返回实际规则和数据来源。",
        parameters={"type": "object", "properties": {"project_id": {"type": "string"}},
                    "required": ["project_id"], "additionalProperties": False}, read_only=True)
    attach_discovery_tools(network, root)
    return network, root
