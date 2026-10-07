# %%
import numpy as np
import pandas as pd

from config import DATA_DIR

# %%
DATA_DIR.mkdir(parents=True,exist_ok=True)

output_path=DATA_DIR/"实验记录.csv"
rng = np.random.default_rng(42)
n_records=100
records=pd.DataFrame({
    "记录编号":[f"{i:03d}" for i in range(1,n_records+1)],
    "项目":rng.choice(["A","B","C"],size=n_records),
    "测量值":rng.integers(50,100,size=n_records),
    "是否有效":rng.choice(["是","否"],size=n_records,p=[0.8,0.2])
})
records.to_csv(output_path,index=False,encoding="utf-8-sig")


