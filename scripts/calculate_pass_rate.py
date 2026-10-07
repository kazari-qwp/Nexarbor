import pandas as pd

from config import DATA_DIR

file_path= DATA_DIR/"实验记录.csv"
records = pd.read_csv(file_path)
valid=records[(records["项目"]=="A")&(records["是否有效"]=="是")]
if len(valid) == 0:
    print("无有效数据")
else:
    pass_rate = (valid["测量值"]>=80).mean()
    print(f"合格率:{pass_rate:.1%}")