import pandas as pd

from config import RECORDS_PATH
from labinsight.analysis import analyze_project
from labinsight.rules import get_project_judge


def analyze_project_tool(project_id):
    """读取实验数据和项目规则，返回统计结果。"""
    if not isinstance(project_id, str):
        raise TypeError("项目编号必须是字符串")

    is_passed = get_project_judge(project_id)
    records = pd.read_csv(
        RECORDS_PATH,
        dtype={
            "记录编号": "string",
            "项目": "string",
            "测量值": "Int64",
            "是否有效": "string",
        },
    )
    return analyze_project(records, project_id, is_passed)


TOOL_FUNCTIONS = {
    "analyze_project": analyze_project_tool,
}
