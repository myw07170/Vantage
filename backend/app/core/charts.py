"""ECharts option builders for the inline report charts.

The frontend renders `spec.option` verbatim, so every label a reader sees on a
chart originates here.
"""
from __future__ import annotations

from typing import Any, Dict, List

PALETTE = {
    "primary": "#7C9885",
    "sun": "#F4E2B8",
    "info": "#8FA8C0",
    "risk": "#CE9A92",
    "soft": "#A8C0A8",
    "ink": "#3A413C",
    "ink2": "#6B746C",
    "line": "#E3E8E3",
}
SERIES = ["#7C9885", "#E0B775", "#8FA8C0", "#CE9A92", "#A8C0A8", "#C2B59B"]
SENTIMENT = {"pos": "#8AB58A", "neu": "#C9CFC9", "neg": "#CE9A92"}
SENTIMENT_LABEL = {"pos": "Positive", "neu": "Neutral", "neg": "Negative"}

_BASE_TEXT = {
    "color": PALETTE["ink2"],
    "fontFamily": "Inter, -apple-system, Segoe UI, sans-serif",
}


def _grid() -> Dict[str, Any]:
    return {"left": 48, "right": 24, "top": 48, "bottom": 36, "containLabel": True}


def _title(text: str) -> Dict[str, Any]:
    return {
        "text": text,
        "left": "center",
        "textStyle": {"color": PALETTE["ink"], "fontSize": 15},
    }


def _axis_label() -> Dict[str, Any]:
    return {"color": PALETTE["ink2"]}


def _axis_line() -> Dict[str, Any]:
    return {"lineStyle": {"color": PALETTE["line"]}}


def feature_radar(
    title: str, dimensions: List[str], series: List[Dict[str, Any]]
) -> Dict[str, Any]:
    indicator = [{"name": d, "max": 100} for d in dimensions]
    data = [
        {
            "value": s["values"],
            "name": s["name"],
            "lineStyle": {"color": SERIES[i % len(SERIES)]},
            "itemStyle": {"color": SERIES[i % len(SERIES)]},
            "areaStyle": {"opacity": 0.12},
        }
        for i, s in enumerate(series)
    ]
    return {
        "title": _title(title),
        "tooltip": {},
        "legend": {"bottom": 0, "textStyle": _BASE_TEXT},
        "radar": {
            "indicator": indicator,
            "splitLine": _axis_line(),
            "splitArea": {"areaStyle": {"color": ["#FAFBF9", "#FFFFFF"]}},
            "axisName": {"color": PALETTE["ink2"]},
        },
        "series": [{"type": "radar", "data": data, "symbolSize": 5}],
    }


def pricing_bar(
    title: str, products: List[str], values: List[float], y_name: str = "$/mo"
) -> Dict[str, Any]:
    return {
        "title": _title(title),
        "tooltip": {"trigger": "axis"},
        "grid": _grid(),
        "xAxis": {
            "type": "category",
            "data": products,
            "axisLine": _axis_line(),
            "axisLabel": _axis_label(),
        },
        "yAxis": {
            "type": "value",
            "name": y_name,
            "splitLine": _axis_line(),
            "axisLabel": _axis_label(),
        },
        "series": [
            {
                "type": "bar",
                "data": values,
                "barWidth": "46%",
                "itemStyle": {
                    "color": PALETTE["primary"],
                    "borderRadius": [8, 8, 0, 0],
                },
            }
        ],
    }


def market_donut(title: str, shares: List[Dict[str, Any]]) -> Dict[str, Any]:
    data = [
        {
            "name": s["name"],
            "value": s["value"],
            "itemStyle": {"color": SERIES[i % len(SERIES)]},
        }
        for i, s in enumerate(shares)
    ]
    return {
        "title": _title(title),
        "tooltip": {"trigger": "item"},
        "legend": {"bottom": 0, "textStyle": _BASE_TEXT},
        "series": [
            {
                "type": "pie",
                "radius": ["42%", "68%"],
                "center": ["50%", "48%"],
                "avoidLabelOverlap": True,
                "label": {"show": False},
                "data": data,
            }
        ],
    }


def sentiment_donut(title: str, overall: Dict[str, int]) -> Dict[str, Any]:
    data = [
        {
            "name": SENTIMENT_LABEL[k],
            "value": overall.get(k, 0),
            "itemStyle": {"color": SENTIMENT[k]},
        }
        for k in ("pos", "neu", "neg")
    ]
    return {
        "title": _title(title),
        "tooltip": {"trigger": "item", "formatter": "{b}: {d}%"},
        "legend": {"bottom": 0, "textStyle": _BASE_TEXT},
        "series": [
            {
                "type": "pie",
                "radius": ["45%", "70%"],
                "center": ["50%", "48%"],
                "label": {"show": False},
                "data": data,
            }
        ],
    }


def platform_bar(title: str, by_platform: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    from app.core.platforms import PLATFORM_LABEL, PLATFORM_ORDER

    plats = [p for p in PLATFORM_ORDER if p in by_platform]
    names = [PLATFORM_LABEL.get(p, p) for p in plats]
    totals = [sum(by_platform[p].values()) for p in plats]
    return {
        "title": _title(title),
        "tooltip": {"trigger": "axis"},
        "grid": _grid(),
        "xAxis": {
            "type": "value",
            "splitLine": _axis_line(),
            "axisLabel": _axis_label(),
        },
        "yAxis": {
            "type": "category",
            "data": list(reversed(names)),
            "axisLabel": _axis_label(),
            "axisLine": _axis_line(),
        },
        "series": [
            {
                "type": "bar",
                "data": list(reversed(totals)),
                "barWidth": "50%",
                "itemStyle": {"color": PALETTE["info"], "borderRadius": [0, 8, 8, 0]},
            }
        ],
    }


def trend_line(
    title: str, x: List[str], series: List[Dict[str, Any]], y_name: str = ""
) -> Dict[str, Any]:
    """Multi-series line chart for anything that moves over time."""
    s = []
    for i, ser in enumerate(series):
        color = SERIES[i % len(SERIES)]
        s.append(
            {
                "name": ser["name"],
                "type": "line",
                "smooth": True,
                "symbol": "circle",
                "symbolSize": 6,
                "lineStyle": {"width": 2.5, "color": color},
                "itemStyle": {"color": color},
                "areaStyle": {"opacity": 0.06, "color": color},
                "data": ser["values"],
            }
        )
    return {
        "title": _title(title),
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0, "textStyle": _BASE_TEXT},
        "grid": _grid(),
        "xAxis": {
            "type": "category",
            "boundaryGap": False,
            "data": x,
            "axisLabel": _axis_label(),
            "axisLine": _axis_line(),
        },
        "yAxis": {
            "type": "value",
            "name": y_name,
            "splitLine": _axis_line(),
            "axisLabel": _axis_label(),
        },
        "series": s,
    }


_FORCE_LABEL = {
    "rivalry": "Competitive rivalry",
    "new_entrants": "Threat of new entrants",
    "substitutes": "Threat of substitutes",
    "buyer_power": "Buyer bargaining power",
    "supplier_power": "Supplier bargaining power",
}
_FORCE_ORDER = [
    "rivalry",
    "new_entrants",
    "substitutes",
    "buyer_power",
    "supplier_power",
]


def five_forces_radar(title: str, forces: Dict[str, Any]) -> Dict[str, Any]:
    """Porter's five forces, 0-100 — higher means more competitive pressure."""
    keys = [k for k in _FORCE_ORDER if isinstance(forces.get(k), (int, float))]
    indicator = [{"name": _FORCE_LABEL[k], "max": 100} for k in keys]
    values = [forces[k] for k in keys]
    return {
        "title": _title(title),
        "tooltip": {},
        "radar": {
            "indicator": indicator,
            "splitLine": _axis_line(),
            "splitArea": {"areaStyle": {"color": ["#FAFBF9", "#FFFFFF"]}},
            "axisName": {"color": PALETTE["ink2"], "fontSize": 11},
        },
        "series": [
            {
                "type": "radar",
                "data": [
                    {
                        "value": values,
                        "name": "Competitive pressure",
                        "lineStyle": {"color": PALETTE["risk"]},
                        "itemStyle": {"color": PALETTE["risk"]},
                        "areaStyle": {"opacity": 0.18, "color": PALETTE["risk"]},
                    }
                ],
                "symbolSize": 5,
            }
        ],
    }


def growth_bar(
    title: str, products: List[str], values: List[float], y_name: str = "%"
) -> Dict[str, Any]:
    """Comparison bars with positive/negative colouring."""
    data = [
        {
            "value": v,
            "itemStyle": {
                "color": PALETTE["primary"] if v >= 0 else PALETTE["risk"],
                "borderRadius": [8, 8, 0, 0] if v >= 0 else [0, 0, 8, 8],
            },
        }
        for v in values
    ]
    return {
        "title": _title(title),
        "tooltip": {"trigger": "axis"},
        "grid": _grid(),
        "xAxis": {
            "type": "category",
            "data": products,
            "axisLine": _axis_line(),
            "axisLabel": _axis_label(),
        },
        "yAxis": {
            "type": "value",
            "name": y_name,
            "splitLine": _axis_line(),
            "axisLabel": _axis_label(),
        },
        "series": [{"type": "bar", "data": data, "barWidth": "46%"}],
    }


def sentiment_timeline(title: str, timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    dates = [t["date"] for t in timeline]

    def ser(key: str) -> Dict[str, Any]:
        return {
            "name": SENTIMENT_LABEL[key],
            "type": "line",
            "stack": "total",
            "smooth": True,
            "areaStyle": {"opacity": 0.25},
            "lineStyle": {"width": 2},
            "itemStyle": {"color": SENTIMENT[key]},
            "data": [t[key] for t in timeline],
        }

    return {
        "title": _title(title),
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0, "textStyle": _BASE_TEXT},
        "grid": _grid(),
        "xAxis": {
            "type": "category",
            "boundaryGap": False,
            "data": dates,
            "axisLabel": _axis_label(),
            "axisLine": _axis_line(),
        },
        "yAxis": {
            "type": "value",
            "splitLine": _axis_line(),
            "axisLabel": _axis_label(),
        },
        "series": [ser("pos"), ser("neu"), ser("neg")],
    }
