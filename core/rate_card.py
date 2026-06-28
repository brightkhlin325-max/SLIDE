"""SSOT 運費費率卡(Rate Card)— 全專案唯一的「升級運送成本」來源。

取代先前散落在 app.py / optimizer.py / model_pipeline.py / explainer.py /
preprocessor.py 的五份重複 dict(B0-3)。

key 以資料實際 order_region 名稱為準(23 區實測):已修正先前四份的錯 key
（"East Asia"→"Eastern Asia"、"North America"→"East of USA"）。
查詢時對 mode/region 做 .strip()，容忍 trailing space（如 "US Center "）。
未列出的區域沿用 DEFAULT_REGION_MULTIPLIER（=1.0，維持現況）。
"""
from typing import Any

DEFAULT_BASE_COST = 80.0
DEFAULT_REGION_MULTIPLIER = 1.0

SHIPPING_BASE_COSTS = {
    "Standard Class": 50.0,
    "Second Class": 80.0,
    "First Class": 120.0,
    "Same Day": 180.0,
}

# 區域係數；key 必須對得上資料的 order_region（已校正）
REGION_MULTIPLIERS = {
    "Western Europe": 1.1,
    "Central America": 0.9,
    "South America": 0.95,
    "Northern Europe": 1.25,
    "Eastern Europe": 1.05,
    "East of USA": 1.15,
    "Eastern Asia": 1.2,
    "Oceania": 1.3,
}


def _key(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def shipping_base_cost(mode: Any) -> float:
    return SHIPPING_BASE_COSTS.get(_key(mode), DEFAULT_BASE_COST)


def region_multiplier(region: Any) -> float:
    return REGION_MULTIPLIERS.get(_key(region), DEFAULT_REGION_MULTIPLIER)


def upgrade_cost(mode: Any, region: Any, ratio: float = 1.0) -> float:
    """升級運送成本 = base(mode) × region_multiplier(region) × ratio。"""
    return round(shipping_base_cost(mode) * region_multiplier(region) * float(ratio), 2)
