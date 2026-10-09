import pandas as pd

from config import DB_PATH, PROJECT_ROOT, RECORDS_PATH
from applications.experiment.tools.analysis import analyze_project
from applications.experiment.rules import get_project_rule, make_judge


def analyze_project_tool(project_id):
    if not isinstance(project_id, str):
        raise TypeError("项目编号必须是字符串")

    # 查询一次，计算和返回结果使用同一份规则
    rule = get_project_rule(project_id)
    if rule is None:
        raise ValueError(f"没有找到项目规则：{project_id}")

    is_passed = make_judge(rule)

    records = pd.read_csv(
        RECORDS_PATH,
        dtype={
            "记录编号": "string",
            "项目": "string",
            "测量值": "Int64",
            "是否有效": "string",
        },
    )

    result = analyze_project(records, project_id, is_passed)

    # 补充实际使用的规则
    result["rule"] = {
        **rule,
        "inclusive": True,
    }

    # 补充数据与规则的来源
    result["sources"] = {
        "records_file": RECORDS_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "rules_database": DB_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "rules_table": "rules",
        "rule_project_id": project_id,
    }

    return result


TOOL_FUNCTIONS = {
    "analyze_project": analyze_project_tool,
}
