"""按目录发现配置包，供搭建者选择；尚不自动替 Agent 做选择。"""
from pathlib import Path
from datanet.core.packages.agent import load_agent_package
from datanet.core.packages.network import load_network_package

def list_packages(directory, kind):
    if kind not in ('agent', 'network'):
        raise ValueError('kind 必须为 agent 或 network')
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    loader = load_agent_package if kind == 'agent' else load_network_package
    result = []
    seen = set()
    for path in sorted(directory.glob('*/package.json')):
        package = loader(path)
        if package.package_id in seen:
            raise ValueError(f'配置包编号重复：{package.package_id}')
        seen.add(package.package_id)
        result.append({'id': package.package_id, 'description': package.description, 'path': str(package.path)})
    return result
