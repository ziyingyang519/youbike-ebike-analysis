# %% [markdown]
# ---
# title: "01 資料整理"
# author: "A"
# ---

# %%
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
from youbike import (load_interim, prepare_stations, add_trip_features,
                     find_question_mark_fixes, apply_name_fixes)

INTERIM = ROOT / "data" / "interim"
EXTERNAL = ROOT / "data" / "external"
PROCESSED = ROOT / "data" / "processed"

# %% [markdown]
# ## 清理原始資料
#
# 原始資料（`data/raw/rawdata_YYYYMM.csv`）每個月約 700–900 萬筆。先在終端機執行一次：
#
# ```bash
# python scripts/prepare_data.py
# ```
#
# 它會把每個月清理後存成 `data/interim/trips_YYYYMM.parquet`（約 40 MB），之後讀取一個月只要不到 1 秒。
#
# 清理規則：
#
# - 刪除時間、站名、時長或車種缺漏的紀錄。
# - 刪除騎乘超過 240 分鐘的紀錄（2026 年 3 月約占 0.09%，高於兩種車的第 99.9 百分位，可能是未正常還車）。
# - 刪除同站借還且少於 1 分鐘的紀錄（約占 0.1%，可能是借車失敗後立刻歸還）。

# %%
report = pd.read_csv(INTERIM / "cleaning_report.csv")
report

# %% [markdown]
# ## 車種分布與站點數
#
# 整年約 8,200 萬筆，一次全部讀進來可能讓記憶體不夠，所以一個月一個月讀、只留彙總結果。

# %%
MONTHS = sorted(f"{p.stem[-6:-2]}-{p.stem[-2:]}" for p in INTERIM.glob("trips_*.parquet"))

shares, rent_all, rent_ebike, name_counts = [], set(), set(), None
for m in MONTHS:
    df = load_interim(INTERIM, months=[m], columns=["rent_station", "return_station", "bike_type"])
    shares.append({"month": m, "rides": len(df), "ebike_share": (df["bike_type"] == "ebike").mean()})
    rent_all |= set(map(str, df["rent_station"].unique()))
    rent_ebike |= set(map(str, df.loc[df["bike_type"] == "ebike", "rent_station"].unique()))
    # 站名是類別型態，直接計數比轉成文字省很多記憶體
    for col in ["rent_station", "return_station"]:
        c = df[col].value_counts()
        c = c[c > 0]
        c.index = c.index.astype(str)
        name_counts = c if name_counts is None else name_counts.add(c, fill_value=0)
    del df

pd.DataFrame(shares).round(3)

# %%
print(f"站點數：{len(rent_all)}，有電輔車借出的站點：{len(rent_ebike)}")

# %% [markdown]
# ## 站名比對
#
# 站點座標來自 YouBike 2.0 即時資訊，請用瀏覽器存成 `data/external/stations.json`。
#
# 原始資料把「瑠、廍、舘」等罕用字寫成「?」，例如「?公公園」其實是「瑠公公園」。先用站點清單比對還原，結果存在 `data/reference/station_name_fixes.csv`（這個檔案會進 git，可以手動補充）。

# %%
stations = prepare_stations(pd.read_json(EXTERNAL / "stations.json"))
REFERENCE = ROOT / "data" / "reference"
fixes = find_question_mark_fixes(name_counts.index, stations["name"]).sort_values("raw_name")
fixes.to_csv(REFERENCE / "station_name_fixes.csv", index=False, encoding="utf-8-sig")
fixes

# %% [markdown]
# 剩下對不上的多半是新北市的站點（跨市騎乘），以及已改名或撤除的台北站點。

# %%
fixed_names = name_counts.rename(index=dict(zip(fixes["raw_name"], fixes["fixed_name"])))
fixed_names = fixed_names.groupby(level=0).sum()
missing = fixed_names[~fixed_names.index.isin(set(stations["name"]))].sort_values(ascending=False)
print(f"對不上的站名：{len(missing)} 個，占借還站次 {missing.sum() / fixed_names.sum():.2%}")
missing.head(30)

# %% [markdown]
# ## 旅次特徵（以 2026 年 3 月為例）
#
# 為了節省記憶體，先隨機抽 20%（約 150 萬筆），結果和用全部資料幾乎相同。

# %%
march = apply_name_fixes(load_interim(INTERIM, months=["2026-03"], sample_frac=0.2), fixes)
march_f = add_trip_features(march, stations)
march_f.groupby("bike_type", observed=True)[["distance_km", "duration_min", "speed_kmh"]].median()
