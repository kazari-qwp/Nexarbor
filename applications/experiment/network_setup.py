"""实验项目的节点配置，存储实现由 datanet 提供。"""

from functools import partial

from config import DB_PATH, RECORDS_PATH
from datanet.nodes.csv_node import CsvNode
from datanet.network import Network
from datanet.nodes.node import Node
from datanet.nodes.sqlite_node import SqliteNode
from applications.experiment.tools.network_tools import RECORD_DTYPES, analyze_project_via_network


def build_lab_network(db_path=DB_PATH, records_path=RECORDS_PATH):
    """每次构建独立的根、存储节点及连接，便于演示和测试。"""
    root = Node("root", "实验项目入口", None)
    rules = SqliteNode(
        "lab_rules", "实验规则", "experiment_rule", db_path, "rules", "project_id"
    )
    records = CsvNode(
        "lab_records", "实验记录", "experiment_record",
        records_path, "记录编号", RECORD_DTYPES,
    )
    root.strong_read_interfaces.extend([rules.interface, records.interface])
    network = Network()
    for node in (root, rules, records):
        network.add_node(node)
    root.tools["analyze_project"] = partial(
        analyze_project_via_network, network=network,
        entry_node_id=root.node_id, scope="integrated",
    )
    return network, root
