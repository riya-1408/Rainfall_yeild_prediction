"""Statistical / analytical layer on top of the integrated dataset."""
import numpy as np
import pandas as pd
from scipy import stats


def _corr(x, y):
    if len(x) < 10 or np.std(x) == 0 or np.std(y) == 0:
        return dict(n=len(x), pearson_r=np.nan, p_value=np.nan, spearman_rho=np.nan)
    r, p = stats.pearsonr(x, y)
    rho, _ = stats.spearmanr(x, y)
    return dict(n=len(x), pearson_r=r, p_value=p, spearman_rho=rho)


def corr_by(df, keys, x="rain_z", y="yield_z", min_n=30):
    """Correlation of rainfall anomaly vs yield anomaly for every group."""
    d = df.dropna(subset=[x, y])
    rows = []
    for k, g in d.groupby(keys):
        if len(g) >= min_n:
            k = k if isinstance(k, tuple) else (k,)
            rows.append({**dict(zip(keys, k)), **_corr(g[x].values, g[y].values)})
    return pd.DataFrame(rows)


def overall_correlation(df):
    d = df.dropna(subset=["rain_z", "yield_z"])
    return {"anomaly_based": _corr(d["rain_z"].values, d["yield_z"].values)}


def extreme_year_impact(df):
    d = df.dropna(subset=["rain_z", "yield_anom_pct"]).copy()
    d["rain_class"] = pd.cut(d["rain_z"], [-np.inf, -1, 1, np.inf], labels=["Deficient (z<-1)", "Normal", "Excess (z>1)"])
    return (d.groupby(["crop", "rain_class"], observed=True)["yield_anom_pct"]
              .agg(mean_yield_change_pct="mean", n="count").reset_index())


def rainfall_trends(annual):
    rows = []
    for (st, d), g in annual.groupby(["state", "district"]):
        if len(g) < 8:
            continue
        lr = stats.linregress(g["year"], g["annual_rain"])
        rows.append(dict(state=st, district=d, mean_annual_rain=g["annual_rain"].mean(),
                         rain_cv=g["annual_rain"].std() / g["annual_rain"].mean(),
                         trend_mm_per_year=lr.slope, p_value=lr.pvalue))
    t = pd.DataFrame(rows)
    t["trend"] = np.where(t["p_value"] >= 0.1, "No significant trend",
                          np.where(t["trend_mm_per_year"] > 0, "Increasing", "Decreasing"))
    return t


def district_stats(df, trends):
    """Per-district rainfall statistics and rain-yield sensitivity (used by the Districts tab)."""
    d = df.dropna(subset=["rain_z", "yield_z", "yield_anom_pct"])
    rows = []
    for (st, dist), g in d.groupby(["state", "district"]):
        if len(g) < 30:
            continue
        r = _corr(g["rain_z"].values, g["yield_z"].values)
        slope = np.polyfit(g["rain_z"], g["yield_anom_pct"], 1)[0]  # % yield change per 1 sigma of rainfall
        rows.append(dict(state=st, district=dist, n_obs=len(g), pearson_r=r["pearson_r"], p_value=r["p_value"],
                         sensitivity_pct_per_sigma=slope))
    out = pd.DataFrame(rows).merge(trends[["state", "district", "mean_annual_rain", "rain_cv", "trend"]])
    prod = df.groupby(["state", "district", "year"])["production"].sum().groupby(["state", "district"]).mean()
    out = out.merge(prod.rename("mean_annual_production").reset_index())
    return out.sort_values("mean_annual_production", ascending=False).reset_index(drop=True)


def seasonal_summary(df):
    return (df.groupby("season").agg(records=("crop", "size"), total_production=("production", "sum"),
                                     avg_yield=("yield", "mean"), avg_season_rain=("season_rain", "mean"))
              .reset_index())


def run_analysis(df, annual):
    trends = rainfall_trends(annual)
    return {
        "overall": overall_correlation(df),
        "corr_crop_season": corr_by(df, ["crop", "season"]),
        "corr_crop": corr_by(df, ["crop"]),
        "corr_state": corr_by(df, ["state"]),
        "extreme": extreme_year_impact(df),
        "trends": trends,
        "districts": district_stats(df, trends),
        "seasonal": seasonal_summary(df),
    }
