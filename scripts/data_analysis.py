import pandas as pd

from config import DATA_DIR


def get_valid_records(records, project_id):
    """有效记录：属于指定项目、标记有效、测量值不缺失。"""
    return records[
        (records["项目"] == project_id) &
        (records["是否有效"] == "是") &
        records["测量值"].notna()
    ]


def count_passed(records, project_id, is_passed):
    valid = get_valid_records(records, project_id)
    return int(valid["测量值"].map(is_passed).sum())


def count_valid(records, project_id):
    return len(get_valid_records(records, project_id))


def count_failed(records, project_id, is_passed):
    return (
        count_valid(records, project_id)
        - count_passed(records, project_id, is_passed)
    )


def calculate_pass_rate(records, project_id, is_passed):
    valid_count = count_valid(records, project_id)

    if valid_count == 0:
        return None

    return count_passed(records, project_id, is_passed) / valid_count


def calculate_valid_rate(records, project_id):
    project_count = len(records[records["项目"] == project_id])

    if project_count == 0:
        return None

    return count_valid(records, project_id) / project_count


if __name__ == "__main__":
    records = pd.read_csv(DATA_DIR / "实验记录.csv")
    rate = calculate_pass_rate(records, "A", lambda x: x >= 80)

    if rate is None:
        print("暂无有效记录")
    else:
        print(f"项目 A 合格率：{rate:.1%}")