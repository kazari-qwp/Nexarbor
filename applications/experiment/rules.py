import sqlite3
from typing import Any

from config import DB_PATH


def get_project_ids():
    """返回规则表中的所有项目编号。"""
    connection = sqlite3.connect(DB_PATH)

    try:
        rows = connection.execute(
            "SELECT project_id FROM rules ORDER BY project_id"
        ).fetchall()
    finally:
        connection.close()

    return [row[0] for row in rows]


def get_project_rule(project_id) -> dict[str, Any] | None:
    """查询项目规则，返回普通字典。"""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        row = connection.execute(
            "SELECT * FROM rules WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    return dict(row)


def make_judge(rule):
    """根据规则字典生成判定函数。"""
    rule_type = rule["rule_type"]
    lower = rule["lower_bound"]
    upper = rule["upper_bound"]

    if rule_type == "at_least":
        if lower is None:
            raise ValueError("规则缺少下限")
        return lambda x: x >= lower

    if rule_type == "at_most":
        if upper is None:
            raise ValueError("规则缺少上限")
        return lambda x: x <= upper

    if rule_type == "between":
        if lower is None or upper is None:
            raise ValueError("规则缺少区间边界")
        if lower > upper:
            raise ValueError("规则下限大于上限")
        return lambda x: lower <= x <= upper

    raise ValueError(f"未知规则类型：{rule_type}")


def get_project_judge(project_id):
    """保留原有接口，其他地方仍然可以使用。"""
    return make_judge(get_project_rule(project_id))
