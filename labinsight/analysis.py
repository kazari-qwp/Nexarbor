def get_valid_records(records, project_id):
    """有效记录：属于指定项目、标记有效、测量值不缺失。"""
    return records[
        records["项目"].eq(project_id).fillna(False) &
        records["是否有效"].eq("是").fillna(False) &
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
    """项目已知的记录作为分母，标记或测量值缺失的记录不计为有效。"""
    project_count = int(records["项目"].eq(project_id).fillna(False).sum())

    if project_count == 0:
        return None

    return count_valid(records, project_id) / project_count

def analyze_project(records, project_id, is_passed):
    valid_count = count_valid(records, project_id)
    passed_count = count_passed(records, project_id, is_passed)
    failed_count = valid_count - passed_count

    if valid_count == 0:
        pass_rate = None
    else:
        pass_rate = passed_count / valid_count

    return {
        "project_id": project_id,
        "valid_count": valid_count,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "pass_rate": pass_rate,
    }
