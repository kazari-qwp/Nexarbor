from pathlib import Path

import numpy as np
import pandas as pd

from config import RECORDS_PATH


def generate_records(
    n_records: int = 100,
    *,
    seed: int | None = 10086,
    projects: tuple[str, ...] = ("A", "B", "C"),
    value_range: tuple[int, int] = (50, 100),
    valid_probability: float = 0.8,
    p: float = 0.01,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """生成实验记录；三列中的每个值独立以概率 p 缺失。

    测量值范围包含两端，可选择保存为 CSV。
    """
    if not isinstance(n_records, int) or isinstance(n_records, bool) or n_records < 0:
        raise ValueError("n_records 必须是非负整数")
    if not projects:
        raise ValueError("projects 不能为空")
    if len(value_range) != 2 or any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in value_range
    ):
        raise ValueError("value_range 必须包含两个整数")
    lower, upper = value_range
    if lower > upper:
        raise ValueError("value_range 的下限不能大于上限")
    if not 0 <= valid_probability <= 1:
        raise ValueError("valid_probability 必须在 0 到 1 之间")
    if not 0 <= p <= 1:
        raise ValueError("p 必须在 0 到 1 之间")

    rng = np.random.default_rng(seed)
    records = pd.DataFrame({
        "记录编号": [f"{i:03d}" for i in range(1, n_records + 1)],
        "项目": rng.choice(projects, size=n_records),
        "测量值": rng.integers(lower, upper + 1, size=n_records),
        "是否有效": rng.choice(
            ["是", "否"], size=n_records,
            p=[valid_probability, 1 - valid_probability],
        ),
    })
    # 可空整数类型保留整数测量值，同时支持 pd.NA。
    records["测量值"] = records["测量值"].astype("Int64")
    for column in ("测量值", "项目", "是否有效"):
        records.loc[rng.random(n_records) < p, column] = pd.NA

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        records.to_csv(output_path, index=False, encoding="utf-8-sig")

    return records


def main() -> None:
    records = generate_records(
        n_records=100,
        p=0.005,
        output_path=RECORDS_PATH,
    )
    print(records.head())


if __name__ == "__main__":
    main()
