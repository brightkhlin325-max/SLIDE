"""產生 demo 上傳範本（50 筆全新訂單），供組員測試「上傳 → 預測」全流程。

平衡版（for demo）：刻意分三群，讓 ROI 散點四象限分明、好看且有說服力：
  - 贏家 A：快運送(Same Day/First)、短天數、正毛利、未延遲 → 低風險、真價值為正（右上/綠）
  - 輸家 B：標準運送、長天數、低/負毛利、延遲      → 高風險、真價值大負（左下/紅）
  - 中間 C：Second Class、混合毛利與延遲           → 中等風險、真價值中性（灰）

仍是全新 Order Id、擾動價/量/折扣/毛利率、Sales 與利潤一致重算、新日期、全新延遲標籤
→ 非驗證集、不偷看答案。並移除出貨後才知道的結果欄（新單本來就沒有）。

輸出兩版到 data/demo_uploads/：
  demo_orders_WITH_delay_answer.csv  （含 Late_delivery_risk＝有延遲答案）
  demo_orders_NO_delay_answer.csv    （不含＝沒延遲答案）

用法：
    conda activate Fastapp
    python scripts/gen_demo_uploads.py
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

np.random.seed(42)
rng = np.random.default_rng(42)
BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "raw" / "DataCoSupplyChainDataset.csv"
OUT = BASE / "data" / "demo_uploads"
N = 50
N_A, N_B, N_C = 18, 17, 15  # 贏家 / 輸家 / 中間，合計 50


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(SRC, encoding="latin-1")
    out = df.sample(N, random_state=42).reset_index(drop=True)
    has = lambda c: c in out.columns  # noqa: E731

    # 三群標記（打散，使 Order Id 不照群連號）
    groups = np.array(["A"] * N_A + ["B"] * N_B + ["C"] * N_C)
    rng.shuffle(groups)
    isA, isB, isC = groups == "A", groups == "B", groups == "C"

    if has("Order Id"):
        out["Order Id"] = [9900001 + i for i in range(N)]

    # ── 運送模式：快(A) / 標準(B) / Second(C) ───────────────────────────
    mode = np.empty(N, dtype=object)
    mode[isA] = rng.choice(["Same Day", "First Class"], isA.sum())
    mode[isB] = "Standard Class"
    mode[isC] = "Second Class"
    if has("Shipping Mode"):
        out["Shipping Mode"] = mode

    # ── 預計天數：短(A) / 長(B) / 中(C) ────────────────────────────────
    days = np.empty(N, dtype=int)
    days[isA] = rng.choice([0, 1], isA.sum())
    days[isB] = 4
    days[isC] = 2
    if has("Days for shipment (scheduled)"):
        out["Days for shipment (scheduled)"] = days

    # ── 單價：贏家偏高、輸家偏低、中間中等 ─────────────────────────────
    price = np.empty(N, dtype=float)
    price[isA] = rng.uniform(60, 200, isA.sum())
    price[isB] = rng.uniform(20, 80, isB.sum())
    price[isC] = rng.uniform(40, 120, isC.sum())
    price = price.round(2)
    pp = "Product Price" if has("Product Price") else (
        "Order Item Product Price" if has("Order Item Product Price") else None)
    if pp:
        out[pp] = price
    if has("Order Item Product Price"):
        out["Order Item Product Price"] = price

    # ── 數量 ───────────────────────────────────────────────────────────
    qty = np.empty(N, dtype=int)
    qty[isA] = rng.integers(2, 6, isA.sum())
    qty[isB] = rng.integers(1, 3, isB.sum())
    qty[isC] = rng.integers(1, 5, isC.sum())
    if has("Order Item Quantity"):
        out["Order Item Quantity"] = qty

    # ── 折扣：贏家低、輸家高、中間混合 ─────────────────────────────────
    disc = np.empty(N, dtype=float)
    disc[isA] = rng.choice([0, 0.05, 0.1], isA.sum())
    disc[isB] = rng.choice([0.15, 0.2, 0.25], isB.sum())
    disc[isC] = rng.choice([0, 0.05, 0.1, 0.15, 0.2], isC.sum())
    disc = disc.round(2)
    if has("Order Item Discount Rate"):
        out["Order Item Discount Rate"] = disc

    # ── 毛利率：贏家正、輸家低/負、中間中性 ───────────────────────────
    ratio = np.empty(N, dtype=float)
    ratio[isA] = rng.uniform(0.25, 0.45, isA.sum())
    ratio[isB] = rng.uniform(-0.15, 0.10, isB.sum())
    ratio[isC] = rng.uniform(0.00, 0.30, isC.sum())
    ratio = ratio.round(3)
    if has("Order Item Profit Ratio"):
        out["Order Item Profit Ratio"] = ratio

    # ── Sales 與利潤一致重算 ───────────────────────────────────────────
    sales = (price * qty * (1 - disc)).round(2)
    for s in ["Sales", "Order Item Total", "Sales per customer"]:
        if has(s):
            out[s] = sales
    if has("Order Item Discount"):
        out["Order Item Discount"] = (price * qty * disc).round(2)
    if has("Order Profit Per Order"):
        out["Order Profit Per Order"] = (sales * ratio).round(2)  # 利潤 = Sales × 毛利率

    if has("order date (DateOrders)"):
        out["order date (DateOrders)"] = [
            (datetime.date(2018, 1, 1) + datetime.timedelta(days=int(d))).strftime("%m/%d/%Y %H:%M")
            for d in rng.integers(0, 330, N)
        ]

    # ── 延遲標籤：贏家=0、輸家=1、中間混合 ─────────────────────────────
    label = np.empty(N, dtype=int)
    label[isA] = 0
    label[isB] = 1
    label[isC] = (rng.uniform(0, 1, isC.sum()) < 0.5).astype(int)

    # 移除出貨後才知道的結果欄（新單尚未發生）
    out = out.drop(columns=[c for c in ["Days for shipping (real)", "Delivery Status", "Benefit per order"] if has(c)])

    labeled = out.copy()
    labeled["Late_delivery_risk"] = label
    unlabeled = out.copy()
    if "Late_delivery_risk" in unlabeled.columns:
        unlabeled = unlabeled.drop(columns=["Late_delivery_risk"])

    labeled.to_csv(OUT / "demo_orders_WITH_delay_answer.csv", index=False, encoding="utf-8-sig")
    unlabeled.to_csv(OUT / "demo_orders_NO_delay_answer.csv", index=False, encoding="utf-8-sig")
    print(f"OK：產生 {N} 筆（平衡版 A贏家={N_A} / B輸家={N_B} / C中間={N_C}）→ {OUT}")
    print("  - demo_orders_WITH_delay_answer.csv（有延遲答案）")
    print("  - demo_orders_NO_delay_answer.csv（沒延遲答案）")
    print(f"延遲標籤分布：{dict(pd.Series(label).value_counts())}")


if __name__ == "__main__":
    main()
