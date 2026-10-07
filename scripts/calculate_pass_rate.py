import pandas as pd

from config import DATA_DIR


def calculate_pass_rate(records,project_id,is_passed):
    valid=records[(records["项目"]==project_id)&(records["是否有效"]=="是")&(records["测量值"].notna())]
    if len(valid) == 0:
        return None
    else:
        return  (valid["测量值"].map(is_passed)).mean()
if __name__ =="__main__":
    records=pd.read_csv(DATA_DIR/"实验记录.csv")
    rate=calculate_pass_rate(records,"A",lambda x:x>=80)
    if rate is None:
        print("暂无有效记录")
    else :
         print(f"项目 A 合格率：{rate:.1%}")