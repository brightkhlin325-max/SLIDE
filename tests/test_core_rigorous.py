"""
SLIDE 自製嚴格單元測試 — 涵蓋先前無專屬測試的核心模組。
全部使用合成 fixtures(不需 data/raw),斷言『契約』而非實作細節。
"""
import sys, os, io
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))


# ─────────────────────────── profit_data_pipeline ───────────────────────────
import profit_data_pipeline as pdp

def _profit_fixture(n=120, seed=0):
    rng = np.random.default_rng(seed)
    cols = {}
    for c in pdp.NUMERIC_FEATURES:
        cols[c] = rng.normal(50, 10, n)
    for c in pdp.CATEGORICAL_FEATURES:
        cols[c] = rng.choice(["A", "B", "C"], n)
    df = pd.DataFrame(cols)
    df[pdp.TARGET_COLUMN] = rng.normal(20, 40, n)
    df[pdp.DATE_COLUMN] = pd.date_range("2017-01-01", periods=n, freq="h").astype(str)
    df[pdp.ORDER_ID_COLUMN] = [f"O{i}" for i in range(n)]
    return df

def test_profit_init_ratio_must_sum_to_one():
    with pytest.raises(pdp.ProfitDataPipelineError):
        pdp.ProfitDataPipeline(train_size=0.6, val_size=0.3, test_size=0.3)

def test_profit_fit_artifacts_no_leakage_and_unknown_code():
    p = pdp.ProfitDataPipeline()
    art = p.fit(_profit_fixture())
    feat = set(art["feature_columns"])
    banned = set(pdp.LEAKAGE_COLUMNS + pdp.PII_COLUMNS + pdp.ID_COLUMNS)
    assert feat.isdisjoint(banned), f"特徵含洩漏/PII/ID:{feat & banned}"
    assert pdp.TARGET_COLUMN not in feat, "目標欄不可在特徵中"
    for c in pdp.CATEGORICAL_FEATURES:
        assert pdp.UNKNOWN_CODE in art["categorical_codes"][c], "類別碼須含 UNKNOWN_CODE"

def test_profit_transform_all_numeric_and_unseen_category_to_unknown():
    p = pdp.ProfitDataPipeline()
    p.fit(_profit_fixture(seed=1))
    test_df = _profit_fixture(n=30, seed=99)
    # 注入沒見過的類別 + 數值缺失
    cat0 = pdp.CATEGORICAL_FEATURES[0]; num0 = pdp.NUMERIC_FEATURES[0]
    test_df.loc[0, cat0] = "ZZZ_UNSEEN"
    test_df.loc[0, num0] = np.nan
    out = p.transform(test_df)
    assert set(out.columns) == set(p.artifacts["feature_columns"] + [pdp.TARGET_COLUMN])
    assert out[p.artifacts["feature_columns"]].select_dtypes(exclude=[np.number]).empty, "特徵須全數值"
    assert out.loc[0, cat0] == pdp.UNKNOWN_CODE, "未見類別須對應 UNKNOWN_CODE"
    assert out[num0].isna().sum() == 0, "數值缺失須被中位數填補"

def test_profit_time_split_counts_and_temporal_order():
    p = pdp.ProfitDataPipeline()
    df = _profit_fixture(n=100)
    tr, va, te = p.time_split(df)
    assert len(tr) + len(va) + len(te) == len(df), "切分筆數須加總等於原始"
    k = pdp._SORT_KEY
    assert pd.to_datetime(tr[k]).max() <= pd.to_datetime(va[k]).min(), "train 不可晚於 val(時間洩漏)"
    assert pd.to_datetime(va[k]).max() <= pd.to_datetime(te[k]).min(), "val 不可晚於 test"


# ─────────────────────────── data_pipeline (延遲) ───────────────────────────
import data_pipeline as dlp
from security_utils import get_leakage_columns

def test_delay_extract_label_raises_without_target():
    pipe = dlp.DataPipeline()
    with pytest.raises(ValueError):
        pipe.extract_label_and_drop_leakage(pd.DataFrame({"x": [1, 2]}))

def test_delay_extract_label_drops_leakage_columns():
    leak = get_leakage_columns()
    assert len(leak) > 0, "應有定義洩漏欄位"
    leak_non_target = [c for c in leak if c != dlp.TARGET_COLUMN]
    assert len(leak_non_target) > 0, "洩漏欄位(排除目標)應存在"
    df = pd.DataFrame({c: [1, 2, 3, 4] for c in leak_non_target})
    df["Shipping Mode"] = ["Standard Class"] * 4
    df[dlp.TARGET_COLUMN] = [0, 1, 0, 1]   # 目標最後設,避免被洩漏欄覆蓋
    X, y = dlp.DataPipeline().extract_label_and_drop_leakage(df)
    assert list(y) == [0, 1, 0, 1]
    assert all(c not in X.columns for c in leak_non_target), "洩漏欄位須被移除"
    assert dlp.TARGET_COLUMN not in X.columns

def test_delay_engineer_features_onehot_and_no_nan():
    n = 20
    df = pd.DataFrame({
        "Shipping Mode": (["Standard Class", "First Class"] * n)[:n],
        "Customer Segment": (["Consumer", "Corporate"] * n)[:n],
        "Order Region": (["Western Europe", "East Asia"] * n)[:n],
        dlp.DATE_COLUMN: pd.date_range("2017-01-01", periods=n, freq="D").astype(str),
    })
    X = dlp.DataPipeline().engineer_features(df)
    assert any(c.startswith("Shipping Mode_") for c in X.columns), "應有 Shipping Mode one-hot"
    assert "Order Region_encoded" in X.columns, "Order Region 應 label-encoded"
    assert int(X.isna().sum().sum()) == 0, "特徵不可有缺失"


# ─────────────────────────── model_pipeline ───────────────────────────
import model_pipeline as mp

def test_model_predict_proba_in_range_and_evaluate_keys():
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(200, 5)), columns=[f"f{i}" for i in range(5)])
    y = pd.Series((X["f0"] + rng.normal(0, 0.3, 200) > 0).astype(int))
    Xtr, Xte, ytr, yte = X[:150], X[150:], y[:150], y[150:]
    m = mp.ModelPipeline()
    m.train(Xtr, ytr, Xte, yte)
    proba = m.predict_proba(Xte)
    assert proba.min() >= 0.0 and proba.max() <= 1.0, "機率須在 [0,1]"
    metrics = m.evaluate(Xte, yte)
    for k in ("roc_auc", "f1", "precision", "recall", "confusion_matrix"):
        assert k in metrics, f"evaluate 缺少 {k}"

def test_risk_thresholds_monotonic():
    t = mp.RISK_THRESHOLDS
    assert t["Low"] < t["Medium"] < t["High"] <= 1.0


# ─────────────────────────── retrainer._resolve_columns ───────────────────────────
import retrainer as rt

def test_resolve_columns_group_and_direct(tmp_path):
    r = rt.ModelRetrainer(base_dir=tmp_path)
    all_cols = ["Shipping Mode_First Class", "Shipping Mode_Same Day",
                "Order Item Profit Ratio", "Order Region_encoded", "Sales"]
    # 顯示名/群組 → 前綴展開
    assert set(r._resolve_columns(["Shipping Mode"], all_cols)) == \
        {"Shipping Mode_First Class", "Shipping Mode_Same Day"}
    # 中文顯示名「利潤比」→ Order Item Profit Ratio
    assert r._resolve_columns(["利潤比"], all_cols) == ["Order Item Profit Ratio"]
    # 直接精確比對
    assert r._resolve_columns(["Sales"], all_cols) == ["Sales"]


# ─────────────────────────── training_store ───────────────────────────
import training_store as ts

def _valid_order_csv(n=5, with_label=True):
    d = {
        "Order Id": list(range(n)),
        "Shipping Mode": ["Standard Class"] * n,
        "Order Region": ["Western Europe"] * n,
        "Category Name": ["Cleats"] * n,
        "Order Profit Per Order": [10.0] * n,   # B0-4：training_store 要求此欄（供收益模型重訓）
    }
    if with_label:
        d["Late_delivery_risk"] = [0, 1] * n
        d["Late_delivery_risk"] = d["Late_delivery_risk"][:n]
    return pd.DataFrame(d)

def test_training_store_requires_label(tmp_path):
    buf = io.StringIO(); _valid_order_csv(with_label=False).to_csv(buf, index=False); buf.seek(0)
    with pytest.raises(ts.TrainingDataError):
        ts.append_training_csv(buf, tmp_path / "store.csv")

def test_training_store_append_accumulates(tmp_path):
    store = tmp_path / "store.csv"
    b1 = io.StringIO(); _valid_order_csv(5).to_csv(b1, index=False); b1.seek(0)
    r1 = ts.append_training_csv(b1, store)
    assert r1["added"] == 5 and r1["total"] == 5
    b2 = io.StringIO(); _valid_order_csv(3).to_csv(b2, index=False); b2.seek(0)
    r2 = ts.append_training_csv(b2, store)
    assert r2["added"] == 3 and r2["total"] == 8, "第二批須累積"

def test_build_combined_counts(tmp_path):
    raw = tmp_path / "raw.csv"; _valid_order_csv(10).to_csv(raw, index=False)
    store = tmp_path / "store.csv"; _valid_order_csv(4).to_csv(store, index=False)
    out = tmp_path / "out.csv"
    info = ts.build_combined_training_file(raw, store, out)
    assert info == {"raw": 10, "accumulated": 4, "total": 14}


# ─────────────────────────── preprocessor.validate_upload_columns ───────────────────────────
import preprocessor as pp

def test_validate_upload_accepts_valid_order_columns():
    res = pp.validate_upload_columns(["Order Id", "Shipping Mode", "Order Region", "Category Name"])
    assert res["matched_known_columns"]

def test_validate_upload_rejects_duplicates():
    with pytest.raises(pp.UploadValidationError):
        pp.validate_upload_columns(["Order Id", "Order Id", "Shipping Mode", "Order Region"])

def test_validate_upload_rejects_non_order_data():
    with pytest.raises(pp.UploadValidationError):
        pp.validate_upload_columns(["foo", "bar", "baz"])


# ─────────────────── 升級:恆等式/乘積式洩漏自動守門器 ───────────────────
# 動機:現有 leakage 檢查只用『欄名』擋(Benefit per order),擋不到
# 「毛利率 × 訂單金額 = 利潤」這種乘積式洩漏。實證在真資料上 corr=1.0。
import itertools

def _detect_identity_leakage(df, target, thr=0.98):
    """回傳與 target 近恆等(|corr|>thr)的單特徵或兩特徵乘積。"""
    y = df[target].astype(float)
    num = df.select_dtypes("number").drop(columns=[target], errors="ignore")
    num = num.loc[:, num.std() > 0]
    hits = []
    for c in num.columns:
        cc = abs(np.corrcoef(num[c], y)[0, 1])
        if cc > thr:
            hits.append(((c,), round(float(cc), 4)))
    for a, b in itertools.combinations(num.columns, 2):
        p = num[a] * num[b]
        if p.std() > 0 and abs(np.corrcoef(p, y)[0, 1]) > thr:
            hits.append(((a, b), round(float(abs(np.corrcoef(p, y)[0, 1])), 4)))
    return hits

def test_leakage_guard_catches_product_form():
    rng = np.random.default_rng(0)
    a = rng.uniform(1, 100, 500); b = rng.uniform(0.1, 0.5, 500)
    df = pd.DataFrame({"a": a, "b": b, "noise": rng.normal(size=500), "target": a * b})
    pairs = [h[0] for h in _detect_identity_leakage(df, "target")]
    assert ("a", "b") in pairs, "守門器須抓到 a*b=target 的乘積式洩漏(margin×total 類)"

def test_leakage_guard_catches_single_identity():
    rng = np.random.default_rng(1)
    t = rng.normal(size=300)
    df = pd.DataFrame({"identity": t * 1.0, "x": rng.normal(size=300), "target": t})
    assert any(h[0] == ("identity",) for h in _detect_identity_leakage(df, "target"))

def test_leakage_guard_clean_data_no_false_positive():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({c: rng.normal(size=400) for c in ["x", "y", "z"]})
    df["target"] = rng.normal(size=400)  # 與特徵無關
    assert _detect_identity_leakage(df, "target") == [], "乾淨資料不該誤報"
