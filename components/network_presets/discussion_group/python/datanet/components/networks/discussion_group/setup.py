"""可配置普通成员数量的装配入口；数据目录按实际节点ID隔离。"""
from hashlib import sha256
from pathlib import Path
from datanet.components.networks.discussion_group.paths import PROJECT_ROOT
from datanet.core.packages import load_network_package
PACKAGE_PATH = Path(__file__).with_name('package.json')

def storage_toolkits(storage_dir=None):
    base = Path(storage_dir) if storage_dir is not None else PROJECT_ROOT / '.models' / 'runtime' / 'discussion_groups'

    def install(network, board):
        board.attach_member_tools()
        directory = base / sha256(board.node_id.encode('utf-8')).hexdigest()[:24]
        ids = [board.node_id, board.project_id, board.notebook_id, board.output_id, *board.members]
        ids += [interface.target_node_id for member in board.members for interface in network.nodes[member].read_interfaces if interface.target_node_id != board.node_id]
        for node_id in ids:
            network.nodes[node_id].file_path = directory / (node_id.rsplit('/', 1)[-1] + '.md')
    return {'discussion_group_storage': install}
TOOLKITS = storage_toolkits()

def build_discussion_group(instance_id='discussion', *, storage_dir=None, member_count=3):
    """只装配网络；Agent 实例由调用者创建。"""
    import json
    from datanet.services.tools.network_management.templates import expand_package
    base = Path(storage_dir) if storage_dir is not None else PROJECT_ROOT / '.models' / 'runtime' / 'discussion_groups'
    spec = json.loads((PACKAGE_PATH.parents[5] / 'members.json').read_text(encoding='utf-8'))
    path, _ = expand_package(PACKAGE_PATH, {'member_count': member_count}, base, spec)
    return load_network_package(path).instantiate(instance_id=instance_id, toolkits=storage_toolkits(storage_dir))
