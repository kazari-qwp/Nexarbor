"""通过网络获取输入，复用纯统计；本模块不直接访问文件和数据库。"""
import pandas as pd
from datanet.core.network import Network
from datanet.components.networks.experiment_analysis.tools.analysis import analyze_project
from datanet.components.networks.experiment_analysis.rules import make_judge
RECORD_DTYPES = {'记录编号': 'string', '项目': 'string', '测量值': 'Int64', '是否有效': 'string'}

def analyze_project_via_network(project_id: str, *, network: Network, entry_node_id: str, strength: int=0):
    if not isinstance(project_id, str):
        raise TypeError('项目编号必须是字符串')
    rules = network.read(entry_node_id, {'method': 'key', 'key': project_id}, strength=strength, data_kind='experiment_rule')
    if rules.status != 'ok':
        raise ValueError(f'规则读取失败：{rules.status}；{rules.errors}')
    if len(rules.items) != 1:
        raise ValueError(f'规则必须恰好一条，实际为 {len(rules.items)} 条')
    records_result = network.read(entry_node_id, {'method': 'filter', 'filters': {'项目': project_id}}, strength=strength, data_kind='experiment_record')
    if records_result.status != 'ok':
        raise ValueError(f'记录读取失败：{records_result.status}；{records_result.errors}')
    if not records_result.sources:
        raise ValueError('记录查询缺少来源')
    required = set(RECORD_DTYPES)
    for source in records_result.sources:
        missing = required - set(source.get('columns', []))
        if missing:
            raise ValueError(f'实验记录缺少字段：{sorted(missing)}')
    for item in records_result.items:
        if required - item.keys():
            raise ValueError('实验记录字段不完整')
    records = pd.DataFrame.from_records(records_result.items, columns=list(RECORD_DTYPES)).astype(RECORD_DTYPES)
    if records['记录编号'].isna().any() or records['记录编号'].duplicated().any():
        raise ValueError('实验记录编号缺失或重复')
    rule = rules.items[0]
    result = analyze_project(records, project_id, make_judge(rule))
    result['rule'] = {**rule, 'inclusive': True}
    result['sources'] = {'rules': rules.sources, 'records': records_result.sources}
    return result
