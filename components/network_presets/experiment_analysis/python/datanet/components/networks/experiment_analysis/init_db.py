import sqlite3
from datanet.components.networks.experiment_analysis.paths import DB_PATH

def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db_path = DB_PATH
    with sqlite3.connect(db_path) as connection:
        connection.execute('\n            CREATE TABLE IF NOT EXISTS rules (\n                project_id TEXT PRIMARY KEY,\n                rule_type TEXT NOT NULL,\n                lower_bound REAL,\n                upper_bound REAL\n            )\n        ')
        connection.executemany('\n            INSERT INTO rules (\n                project_id,\n                rule_type,\n                lower_bound,\n                upper_bound\n            )\n            VALUES (?, ?, ?, ?)\n            ON CONFLICT(project_id) DO NOTHING\n            ', [('A', 'at_least', 80, None), ('B', 'between', 40, 60), ('C', 'at_most', None, 20)])
    connection.close()
    print(f'数据库初始化完成：{db_path}')
if __name__ == '__main__':
    main()
