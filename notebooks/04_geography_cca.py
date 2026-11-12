# %% [markdown]
# ---
# title: "04 地理條件與電輔車使用"
# author: "C"
# ---

# %% [markdown]
# 研究問題 3：站點的地理條件和電輔車使用型態有什麼關係？

# %%
from pathlib import Path
import pandas as pd

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
EXTERNAL = ROOT / "data" / "external"
SEED = 42

# %% [markdown]
# ## 地理變數
#
# | 變數 | 來源 | 狀態 |
# |---|---|---|
# | 站點海拔、周邊坡度 | 內政部 20m DEM | TODO |
# | 到捷運站距離 | TDX 或 OpenStreetMap | TODO |
# | 到市中心距離 | 以臺北車站為中心計算 | TODO |
# | 車柱數 | YouBike 即時資訊 | 已有 |
#
# ## CCA：地理條件組 × 使用型態組
#
# TODO
#
# ## 地圖
#
# TODO：站點類型地圖（folium）。
