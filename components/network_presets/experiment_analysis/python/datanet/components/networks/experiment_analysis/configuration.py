"""实验规则节点实例配置。"""
from datanet.components.networks.experiment_analysis.paths import DB_PATH
from datanet.components.nodes.sqlite_node import SqliteNode
rule_node = SqliteNode(node_id='lab_rules', name='实验规则', data_kind='experiment_rule', db_path=DB_PATH, table_name='rules', key_column='project_id')
