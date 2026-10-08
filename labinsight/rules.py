import sqlite3

from config import DB_PATH


def get_project_judge(project_id):
    """根据项目编号查询规则，返回合格判定函数。"""

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rule = connection.execute(
            "SELECT * FROM rules WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    finally:
        connection.close()

    if rule is None:
        raise ValueError(f"没有找到项目规则：{project_id}")

    rule_type = rule["rule_type"]

    if rule_type == "at_least":
        lower = rule["lower_bound"]

        if lower is None:
            raise ValueError(f"项目 {project_id} 缺少下限")

        return lambda x: x >= lower

    if rule_type == "at_most":
        upper = rule["upper_bound"]

        if upper is None:
            raise ValueError(f"项目 {project_id} 缺少上限")

        return lambda x: x <= upper

    if rule_type == "between":
        lower = rule["lower_bound"]
        upper = rule["upper_bound"]

        if lower is None or upper is None:
            raise ValueError(f"项目 {project_id} 缺少区间边界")

        if lower > upper:
            raise ValueError(f"项目 {project_id} 的下限大于上限")

        return lambda x: lower <= x <= upper

    raise ValueError(f"未知规则类型：{rule_type}")