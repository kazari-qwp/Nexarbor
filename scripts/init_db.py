import sqlite3

from config import DB_PATH


def main():
    # 确保保存数据库的目录存在
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    db_path = DB_PATH

    # 文件不存在时，connect 会自动创建数据库文件
    with sqlite3.connect(db_path) as connection:
        # 创建规则表；已经存在则跳过
        connection.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                project_id TEXT PRIMARY KEY,
                rule_type TEXT NOT NULL,
                lower_bound REAL,
                upper_bound REAL
            )
        """)

        # 写入初始规则；项目已经存在则跳过
        connection.executemany(
            """
            INSERT INTO rules (
                project_id,
                rule_type,
                lower_bound,
                upper_bound
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id) DO NOTHING
            """,
            [
                ("A", "at_least", 80, None),
                ("B", "between", 40, 60),
                ("C", "at_most", None, 20),
            ],
        )

    connection.close()
    print(f"数据库初始化完成：{db_path}")


if __name__ == "__main__":
    main()