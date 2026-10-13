"""在项目根目录运行 python -m datanet.components.networks.experiment_analysis.debug.demo_sqlite_node A；不请求模型。"""
import argparse
import json
from dataclasses import asdict
from datanet.components.networks.experiment_analysis.configuration import rule_node

def main():
    parser = argparse.ArgumentParser(description='演示配置为实验规则的 SQLite 节点')
    parser.add_argument('project_id', nargs='?', default='A')
    args = parser.parse_args()
    output = {'rule_node': rule_node.describe(), 'rule_result': asdict(rule_node.read({'method': 'key', 'key': args.project_id}))}
    print(json.dumps(output, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
