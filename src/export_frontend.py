"""Serialise the analytics and ML results into frontend/data.js (loaded by frontend/index.html)."""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import config as C


def _san(o):
    if isinstance(o, dict):
        return {str(k): _san(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_san(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return round(float(o), 4) if np.isfinite(o) else None
    return o


def _pred(ml):
    T = lambda x: str(x).title()
    return {
        "meta": ml["meta"], "regression": ml["regression"], "classification": ml["classification"],
        "combos": [{**c, "state": T(c["state"]), "district": T(c["district"]),
                    "key": "|".join([T(c["state"]), T(c["district"]), c["crop"], c["season"]])} for c in ml["combos"]],
    }


def _rain_by_crop_season(integ):
    """Mean season rainfall per (state, crop, season, year), taken over the districts that actually grow that crop.
    This is what makes the Rainfall tab respond to the Crop and Season filters."""
    g = integ.groupby(["state", "crop", "season", "year"])["season_rain"].mean().reset_index()
    return [[str(s).title(), c, se, int(y), round(float(v), 1)] for s, c, se, y, v in g.itertuples(index=False)]


def _monthly_by_crop(integ, monthly):
    """Monthly rainfall profile per (state, crop), over the districts that grow that crop."""
    grow = integ[["state", "district", "crop"]].drop_duplicates()
    m = monthly.merge(grow, on=["state", "district"])
    out = {}
    for (s, c), g in m.groupby(["state", "crop"]):
        out[f"{str(s).title()}|{c}"] = g.groupby("month")["rain"].mean().reindex(C.MONTHS).tolist()
    return out


def _grow(integ):
    """Which district grows which crop in which season (used to filter the district tables)."""
    g = integ[["state", "district", "crop", "season"]].drop_duplicates()
    return [[str(s).title(), str(d).title(), c, se] for s, d, c, se in g.itertuples(index=False)]


def build(integ, annual, monthly, res, cube, overall_r, ml, sample):
    T = lambda s: str(s).title()
    dist = res["districts"].copy()
    dist["state"], dist["district"] = dist["state"].map(T), dist["district"].map(T)

    prod = integ.groupby(["state", "district", "year"])["production"].sum().reset_index()
    dy = prod.merge(annual, on=["state", "district", "year"], how="outer").sort_values("year")
    district_year = {f"{T(s)}|{T(d)}": g[["year", "production", "annual_rain"]].values.tolist()
                     for (s, d), g in dy.groupby(["state", "district"])}

    data = {
        "meta": {"sample": bool(sample), "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")},
        "filters": {"states": sorted({T(k[0]) for k in cube}), "crops": sorted({k[1] for k in cube}),
                    "seasons": sorted({k[2] for k in cube}), "years": [int(min(k[3] for k in cube)), int(max(k[3] for k in cube))]},
        "cube": [[T(k[0]), k[1], k[2], int(k[3]), round(float(v[0]), 1), round(float(v[1]), 1)] for k, v in cube.items()],
        "rain_state_year": [[T(s), int(y), m] for (s, y), m in annual.groupby(["state", "year"])["annual_rain"].mean().items()],
        "rain_crop_season": _rain_by_crop_season(integ),
        "rain_monthly_crop": _monthly_by_crop(integ, monthly),
        "grow": _grow(integ),
        "season_months": {k: [C.MONTHS[m - 1] for m in v] for k, v in C.SEASON_MONTHS.items()},
        "rain_monthly": {T(s): g.groupby("month")["rain"].mean().reindex(C.MONTHS).tolist() for s, g in monthly.groupby("state")},
        "months": C.MONTHS,
        "district_year": district_year,
        "districts": dist.to_dict("records"),
        "corr_crop": res["corr_crop"].to_dict("records"),      # used by the Overview insights
        "extreme": res["extreme"].rename(columns={"rain_class": "cls"}).astype({"cls": str}).to_dict("records"),
        "overall_r": overall_r,
        "pred": _pred(ml),
    }
    C.FRONT.mkdir(exist_ok=True)
    (C.FRONT / "data.js").write_text("window.DATA = " + json.dumps(_san(data), separators=(",", ":")) + ";\n", encoding="utf-8")
