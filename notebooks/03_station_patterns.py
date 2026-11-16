# %% [markdown]
# ---
# title: "03 站點型態"
# author: "B"
# ---

# %% [markdown]
# 研究問題 2：各站點的電輔車使用比例與時間型態可以分成哪幾類？

# %%
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from youbike import station_hour_counts, STUDY_MONTHS, SEED

INTERIM = ROOT / "data" / "interim"

# %% [markdown]
# ## 建構站點使用矩陣
#
# 研究期間為 2026 年 3–6 月（`STUDY_MONTHS`）。`station_hour_counts` 一次只讀一個月，結果是長表：站點 × 平日／假日 × 小時 × 車種的借車次數。

# %%
counts = station_hour_counts(INTERIM, months=STUDY_MONTHS)
counts.head()

# %% [markdown]
# 每列一個站點，欄位為平日／假日 × 24 小時的電輔車借車比例。

# %%
wide = counts.pivot_table(index=["rent_station", "day_type", "rent_hour"],
                          columns="bike_type", values="n", fill_value=0, observed=True)
wide["ebike_share"] = wide["ebike"] / (wide["ebike"] + wide["regular"])
ebike_share = wide["ebike_share"].unstack(["day_type", "rent_hour"])
ebike_share.shape

# %% [markdown]
# TODO：排除借車量太少的站點（例如一年少於 1,000 次）與非一般站點（例如「客服中心」），處理缺值。
#
# ## PCA
#
# TODO
#
# ## 分群（階層式、K-means）與 MDS
#
# TODO：輪廓係數選群數，bootstrap 檢查穩定度。
#
# ## CA：行政區 × 站點類型
#
# TODO
