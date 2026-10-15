"""根节点调用工具，经网络读取规则与记录；不请求模型。"""
import argparse
import json
from datanet.components.networks.experiment_analysis.network_setup import build_lab_network

def main():
    parser = argparse.ArgumentParser(description='通过节点网络计算项目合格率')
    parser.add_argument('project_id', nargs='?', default='A')
    args = parser.parse_args()
    _, root = build_lab_network()
    try:
        result = root.invoke_tool('analyze_project', project_id=args.project_id)
    except (ValueError, TypeError) as error:
        parser.exit(1, f'分析失败：{error}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
if __name__ == '__main__':
    main()
