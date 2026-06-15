# 資料一致性 / 月份修復 / 上傳驗證 — 程式碼邏輯說明

> 本文件說明「資料端一致性修復」這個 PR 的每一處改動的**邏輯與原因**，供審查與後續維護參考。
> 對應分支：`fix/data-consistency-monthly`

## 背景：為什麼要改

1. **月份圖卡住**：隊友以「validation split」重訓後重產的 `predictions.csv` **少了 `order_date` 欄位**，導致 `/api/chart/monthly` 回 500、前端卡「載入中」。
2. **訓練/服務不一致（問題四）**：訓練管線 `data_pipeline` 與上傳/服務管線 `preprocessor` 是兩套各自寫的特徵工程，會漂移：
   - 缺值填補：訓練用「中位數」，服務用「0」。
   - Label 編碼器來源不同（訓練端 fit vs `build_mappings` 對原始全集 fit）。
   - 日期缺值哨兵：訓練 `-1`，服務 `0/6/12`。
3. **上傳零驗證**：`predict_uploaded_csv` 對任何輸入「靜默硬吞」——連 `foo,bar,baz` 都補成全 0、算出假的 High，不報錯。

## 改動總覽

| 檔案 | 改動 | 原因 |
|---|---|---|
| `data/processed/predictions.csv` | 用**現有模型**重產，補上 `order_date`（27,078 列 / 37 月） | 修月份圖；不重訓、不動隊友模型 |
| `core/data_pipeline.py` | 保存 `feature_medians` + `label_classes` 到 `models/serving_artifacts.json` | 讓服務端能用「與訓練相同」的填補值與編碼（SSOT） |
| `core/preprocessor.py` | ①載入 serving_artifacts 用訓練中位數填數值、用訓練編碼器類別 ②日期哨兵改 `-1` ③缺日期不再捏造假日期 ④新增上傳驗證閘門 | 解問題四 bug1/2/4 + A補強 + C |
| `app.py` | `/api/upload` 先呼叫 `validate_upload_columns`，不過回 **400** | C：擋掉非訂單資料/重複欄，不再靜默算垃圾 |

## 細節邏輯

### 1. 重產 predictions.csv（保留隊友模型，只補 order_date）
- 流程：`DataPipeline.run()`（確定性 `random_state` 切分，`extract_metadata` 已含 order_date）→ 載入**現有** `xgboost_model.json` → `ModelPipeline._save_predictions()`。
- 因為「同一模型 + 同一切分」，p_late 與舊檔一致，等於**只多了 order_date 欄**。不訓練、不覆寫模型與指標。

### 2. SSOT 一致化產物 `models/serving_artifacts.json`
- 訓練時（`data_pipeline.engineer_features`）擷取 `X.median()` 與各 `LabelEncoder.classes_`，由 `save_serving_artifacts()` 寫檔。
- 服務時（`preprocessor.predict_uploaded_csv`）載入：
  - **bug1**：數值缺值用 `serving_medians[col]` 填（取代原本 0）。
  - **bug2**：Label 編碼用 `serving_label_classes[col]`（取代 `build_mappings` 的 `feature_mapping.json` 類別）。
- **回退機制**：若 artifact 不存在，行為回退到舊邏輯，不會壞掉。

### 3. 日期一致（bug4）與不捏造（A補強）
- 服務端日期特徵缺值哨兵改 `-1`，與訓練端 `fillna(-1)` 對齊。
- `order_date` metadata 缺日期時改填 `pd.NaT`（留空），不再捏造 `6/10/2026 12:00`。
- **不丟資料**：缺日期的 row 仍正常預測、仍出現在所有清單；只是月份圖無法把它歸到某個月。

### 4. 上傳驗證閘門（C）
- `validate_upload_columns(原始表頭)`：
  - 偵測**重複欄位** → 400。
  - 比對**已知訂單欄位**，少於門檻（預設 3）→ 視為非訂單資料 → 400。
- `app.py /api/upload` 在標準化**之前**先驗證；`UploadValidationError` → HTTP 400。

## 驗證結果（單元 10/10 PASS）
- bug1：`p(缺數值欄)=0.9612 == p(填中位數)0.9612 ≠ p(填0)0.9951` → 確認改用中位數。
- bug2：載入訓練編碼器類別（Order Region 23 / Category 50 / Country 164）。
- bug4/A：缺日期 row 保留、order_date 留空（非捏造）。
- C：`foo,bar,baz`、重複欄被擋；正常訂單欄通過。
- app:app 載入；predictions.csv 含 order_date、27,078 列。
- 端對端：`/api/chart/monthly` 200、37 月有資料。

## 已知 / 後續
- **bug3（未見類別）**：上傳出現訓練未見過的類別時，one-hot 靜默為全 0、label 取 fallback 0。屬可接受行為，已於此記錄；未來可加警告計數。
- **乙（下一個 PR）**：上傳分流（只預測 vs 可進訓練）、累積驗證過的訓練資料、重訓吃「原始+累積」資料並走既有 adopt/discard。
