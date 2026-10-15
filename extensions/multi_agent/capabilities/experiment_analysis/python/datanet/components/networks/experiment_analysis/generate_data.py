from pathlib import Path
import numpy as np
import pandas as pd
from datanet.components.networks.experiment_analysis.paths import RECORDS_PATH
from datanet.components.networks.experiment_analysis.rules import get_project_ids, get_project_judge

def generate_records(n_records: int=100, *, seed: int | None=10086, value_range: tuple[int, int]=(0, 100), valid_probability: float=0.8, missing_probability: float=0.005, pass_probability_mean: float=0.8, pass_probability_variance: float=0.01, output_path: str | Path | None=None) -> pd.DataFrame:
    """使用全部项目规则生成记录。

    每个项目抽取一个合格概率 p，并将其限制在 [0, 1]。
    p 的原始正态分布均值为 0.8、方差为 0.1（限制后分布会改变）。
    测量值为 value_range 内的整数，范围包含两端。
    三列中的每个单元格独立以 missing_probability 的概率缺失。
    """
    if not isinstance(n_records, int) or isinstance(n_records, bool) or n_records < 0:
        raise ValueError('n_records 必须是非负整数')
    if len(value_range) != 2 or any((not isinstance(value, int) or isinstance(value, bool) for value in value_range)):
        raise ValueError('value_range 必须包含两个整数')
    lower, upper = value_range
    if lower > upper:
        raise ValueError('value_range 的下限不能大于上限')
    if not 0 <= valid_probability <= 1:
        raise ValueError('valid_probability 必须在 0 到 1 之间')
    if not 0 <= missing_probability <= 1:
        raise ValueError('missing_probability 必须在 0 到 1 之间')
    if not np.isfinite(pass_probability_mean) or not 0 <= pass_probability_mean <= 1:
        raise ValueError('pass_probability_mean 必须在 0 到 1 之间')
    if not np.isfinite(pass_probability_variance) or pass_probability_variance < 0:
        raise ValueError('pass_probability_variance 必须是非负有限数')
    projects = get_project_ids()
    if not projects:
        raise ValueError('规则表中没有项目，请先添加项目规则')
    rng = np.random.default_rng(seed)
    candidates = np.arange(lower, upper + 1)
    probabilities = {}
    value_pools = {}
    for project_id in projects:
        judge = get_project_judge(project_id)
        passed = np.array([judge(int(value)) for value in candidates], dtype=bool)
        p = float(np.clip(rng.normal(pass_probability_mean, np.sqrt(pass_probability_variance)), 0, 1))
        passing_values = candidates[passed]
        failing_values = candidates[~passed]
        if p > 0 and (not len(passing_values)):
            raise ValueError(f'项目 {project_id} 在测量值范围内没有合格值，请调整 value_range')
        if p < 1 and (not len(failing_values)):
            raise ValueError(f'项目 {project_id} 在测量值范围内没有不合格值，请调整 value_range')
        probabilities[project_id] = p
        value_pools[project_id] = (passing_values, failing_values)
    project_values = rng.choice(projects, size=n_records)
    measurement_values = np.empty(n_records, dtype=int)
    for project_id in projects:
        indices = np.flatnonzero(project_values == project_id)
        passed = rng.random(len(indices)) < probabilities[project_id]
        passing_values, failing_values = value_pools[project_id]
        if passed.any():
            measurement_values[indices[passed]] = rng.choice(passing_values, size=int(passed.sum()))
        if (~passed).any():
            measurement_values[indices[~passed]] = rng.choice(failing_values, size=int((~passed).sum()))
    records = pd.DataFrame({'记录编号': [f'{i:03d}' for i in range(1, n_records + 1)], '项目': project_values, '测量值': pd.array(measurement_values, dtype='Int64'), '是否有效': rng.choice(['是', '否'], size=n_records, p=[valid_probability, 1 - valid_probability])})
    for column in ('测量值', '项目', '是否有效'):
        records.loc[rng.random(n_records) < missing_probability, column] = pd.NA
    records.attrs['pass_probabilities'] = probabilities
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        records.to_csv(output_path, index=False, encoding='utf-8-sig')
    return records

def main() -> None:
    records = generate_records(n_records=100, output_path=RECORDS_PATH)
    print('各项目合格概率：', records.attrs['pass_probabilities'])
    print(records.head())
    print(f'已保存：{RECORDS_PATH}')
if __name__ == '__main__':
    main()
