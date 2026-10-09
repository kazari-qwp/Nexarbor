"""实验项目的节点配置，存储实现由 datanet 提供。"""

from functools import partial
from pathlib import Path

from config import NETWORK_PATH
from datanet.serialization import load_network
from applications.experiment.tools.network_tools import analyze_project_via_network


def build_lab_network(db_path=None, records_path=None, *, config_path=NETWORK_PATH):
    """结构从配置加载；可覆盖数据路径以使用独立测试数据。"""
    network = load_network(config_path)
    root = network.nodes["root"]
    if db_path is not None:
        network.nodes["lab_rules"].db_path = Path(db_path).resolve()
    if records_path is not None:
        network.nodes["lab_records"].file_path = Path(records_path).resolve()
    root.tools["analyze_project"] = partial(
        analyze_project_via_network, network=network,
        entry_node_id=root.node_id, scope="integrated",
    )
    return network, root
