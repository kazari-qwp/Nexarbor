"""在项目根目录运行 python -m datanet.components.networks.experiment_analysis.debug.demo_csv_node [记录编号]。"""
import argparse
from datanet.components.networks.experiment_analysis.paths import RECORDS_PATH
from datanet.components.nodes.csv_node import CsvNode

def main():
    parser = argparse.ArgumentParser(description='按编号读取一条实验记录')
    parser.add_argument('key', nargs='?', default='001', help='字符串记录编号')
    args = parser.parse_args()
    node = CsvNode(node_id='lab_records', name='实验记录', data_kind='experiment_record', file_path=RECORDS_PATH, key_column='记录编号', dtype={'项目': 'string', '测量值': 'Int64', '是否有效': 'string'})
    result = node.read({'method': 'key', 'key': args.key})
    print(result.status)
    print(result.items)
    print(result.sources)
    print(result.errors)
if __name__ == '__main__':
    main()
