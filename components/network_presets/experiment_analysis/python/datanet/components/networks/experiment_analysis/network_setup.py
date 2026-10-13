"""实例化实验网络拼图，可覆盖存储路径以使用独立测试数据。"""
from pathlib import Path
from datanet.components.networks.experiment_analysis.paths import NETWORK_PATH
from datanet.core.packages import load_network_package
from datanet.components.networks.experiment_analysis.toolkit import TOOLKITS

def build_lab_network(db_path=None, records_path=None, *, config_path=NETWORK_PATH):
    network, mounted = load_network_package(config_path).instantiate(toolkits=TOOLKITS)
    root = network.nodes[mounted.entry_points['root']]
    if db_path is not None:
        network.nodes[mounted.node_ids['lab_rules']].db_path = Path(db_path).resolve()
    if records_path is not None:
        network.nodes[mounted.node_ids['lab_records']].file_path = Path(records_path).resolve()
    return (network, root)
