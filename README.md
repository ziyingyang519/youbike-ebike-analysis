# YouBike 電輔車與一般車使用差異之多變量分析

探索式多變量資料分析（Exploratory Multivariate Data Analysis）期末專題。

**研究問題**：台北 YouBike 2.0 的電輔車，是讓人騎得更遠、去不同的地方，還是只是取代原本的一般車旅次？

## 專案結構

```
├── _quarto.yml            Quarto 網站設定（輸出到 docs/，給 GitHub Pages 用）
├── index.qmd              專題首頁
├── notebooks/
│   ├── 01_data_prep.qmd        資料整理（A）
│   ├── 02_trip_level.qmd       旅次分析：MANOVA、LDA／QDA／分類樹（A）
│   ├── 03_station_patterns.qmd 站點型態：PCA、分群、MDS、CA（B）
│   └── 04_geography_cca.qmd    地理條件：CCA、地圖（C）
├── src/youbike/           共用程式：下載、清理、特徵計算
├── scripts/
│   ├── download_data.py   下載原始資料
│   └── prepare_data.py    清理原始資料，存成 parquet
├── tests/                 測試
├── data/                  資料（不放進 git）
│   ├── raw/               原始租借紀錄（rawdata_YYYYMM.csv）
│   ├── interim/           清理後的每月資料（trips_YYYYMM.parquet）
│   ├── external/          站點資訊、地形、日曆
│   └── processed/         清理後的資料
├── figures/
└── AI_DISCLOSURE.md       AI 使用聲明
```

## 開始使用

### 在自己的電腦

```bash
git clone <repo 網址>
cd youbike-ebike-analysis
python -m venv .venv
source .venv/bin/activate          # Windows：.venv\Scripts\activate
pip install -r requirements.txt

python scripts/download_data.py --month 2026-03   # 下載一個月的資料（或手動放到 data/raw/rawdata_YYYYMM.csv）
python scripts/prepare_data.py                     # 清理每個月並存成 data/interim/trips_YYYYMM.parquet
pytest                                             # 確認程式正常
quarto preview                                     # 預覽網站
```

需要另外安裝 [Quarto](https://quarto.org/docs/get-started/)。

### 在 Google Colab

```python
!git clone <repo 網址>
%cd youbike-ebike-analysis
!pip install -q -r requirements.txt
!python scripts/download_data.py --month 2026-03
```

Colab 不能直接開 `.qmd`。在 Colab 試寫程式沒問題，但最後要把程式碼貼回對應的 `.qmd` 檔，才符合課程繳交要求。

## 協作規則

1. 每個人只改自己負責的 `.qmd` 檔，避免衝突。
2. 共用的函式放在 `src/youbike/`，修改前先在群組說一聲，並跑一次 `pytest`。
3. 資料不放進 git，每個人用 `scripts/download_data.py` 自己下載。
4. 固定亂數種子 `SEED = 42`。
5. 使用 AI 時記錄在 `AI_DISCLOSURE.md`。

## 讀取資料

原始資料每個月約 700–900 萬筆（0.5–0.9 GB），不要直接用 `pd.read_csv` 讀整個檔案。先執行 `scripts/prepare_data.py`，之後在分析檔中：

```python
from youbike import load_interim, station_hour_counts

march = load_interim("data/interim", months=["2026-03"])                  # 一個月，不到 1 秒
ebike = load_interim("data/interim", bike_type="ebike", sample_frac=0.05)  # 整年電輔車的 5% 抽樣
counts = station_hour_counts("data/interim")                               # 整年的站點 × 時段借車次數
```

清理規則：刪除缺漏資料、騎乘超過 240 分鐘的紀錄、同站借還且少於 1 分鐘的紀錄。各月刪除筆數記錄在 `data/interim/cleaning_report.csv`。

## 資料說明

租借紀錄欄位（以 2026-07 檔案確認）：

| 欄位 | 內容 | 注意 |
|---|---|---|
| `rent_time`, `return_time` | 借還時間 | 只精確到小時 |
| `rent_station`, `return_station` | 借還站名 | 只有中文站名，需與站點資訊比對取得座標 |
| `rent` | 騎乘時長 | 精確到秒 |
| `bike_type` | 車種 | 電輔車／一般車 |
| `infodate` | 日期 | |

## 資料來源

- 臺北市交通局，[臺北市公共自行車2.0租借紀錄](https://data.taipei/dataset/detail?id=c5924c17-25db-4f1e-99c4-f8ada40f2445)
- YouBike 2.0 即時站點資訊
- 內政部，20 公尺網格數值地形模型
- 行政院人事行政總處，政府行政機關辦公日曆表

## 參考文獻

- Liu, H.-C., & Lin, J.-J. (2019). Associations of built environments with spatiotemporal patterns of public bicycle use. *Journal of Transport Geography, 74*, 299–312. https://doi.org/10.1016/j.jtrangeo.2018.12.010

## 授權

- 程式碼採用 [MIT License](LICENSE)。
- 資料不包含在本 repo 中。資料來自政府開放資料，依「[政府資料開放授權條款－第1版](https://data.gov.tw/license)」使用，引用時請註明原始提供機關。
