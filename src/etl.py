"""ETL: load -> clean -> transform -> integrate crop and rainfall data."""
import difflib
import re

import numpy as np
import pandas as pd

from . import config as C


# ------------------------------------------------------------------ helpers
def standardize(df):
    """Rename raw headers to canonical names using config.ALIASES."""
    ren = {c: C.ALIASES.get(re.sub(r"[^a-z0-9]", "", str(c).lower()), c) for c in df.columns}
    return df.rename(columns=ren)


def clean_name(s):
    """UPPER-case, strip punctuation / the word DISTRICT / extra spaces."""
    s = s.astype(str).str.upper().str.replace(r"[^A-Z0-9 ]", " ", regex=True)
    return s.str.replace(r"\bDISTRICT\b", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()


def _map_names(src, tgt, cutoff):
    tgt = sorted(set(tgt))
    out = {}
    for s in set(src):
        hit = [s] if s in tgt else difflib.get_close_matches(s, tgt, n=1, cutoff=cutoff)
        out[s] = hit[0] if hit else None
    return out


# ------------------------------------------------------------------ crop
def clean_crop(df, log):
    df = standardize(df)
    need = ["state", "district", "year", "season", "crop", "area", "production"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise ValueError(f"Crop file is missing columns {miss}. Add aliases in src/config.py")
    df = df[need].copy()
    log["crop_rows_raw"] = len(df)
    for c in ["year", "area", "production"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna()
    log["crop_dropped_missing"] = log["crop_rows_raw"] - len(df)

    df["state"], df["district"] = clean_name(df["state"]), clean_name(df["district"])
    df["season"] = df["season"].astype(str).str.upper().str.strip()
    df["crop"] = df["crop"].astype(str).str.strip().str.title()
    df["year"] = df["year"].astype(int)

    n = len(df)
    df = df[(df["area"] > 0) & (df["production"] > 0)]
    log["crop_dropped_nonpositive"] = n - len(df)

    n = len(df)  # merge duplicate keys
    df = df.groupby(["state", "district", "year", "season", "crop"], as_index=False)[["area", "production"]].sum()
    log["crop_duplicates_merged"] = n - len(df)

    df["yield"] = df["production"] / df["area"]
    ly = np.log(df["yield"])
    med = ly.groupby(df["crop"]).transform("median")
    mad = (ly - med).abs().groupby(df["crop"]).transform("median") * 1.4826
    bad = (ly - med).abs() > 6 * mad.clip(lower=0.05)  # robust outlier rule per crop
    log["crop_yield_outliers_removed"] = int(bad.sum())
    df = df[~bad]
    log["crop_rows_clean"] = len(df)
    return df.reset_index(drop=True)


# ------------------------------------------------------------------ rainfall
def clean_rain(df, log):
    """Returns (monthly_long, seasonal_long, annual)."""
    df = standardize(df)
    if "month" in df.columns and "rainfall" in df.columns and not set(C.MONTHS) & set(df.columns):
        m = df["month"].astype(str).str.strip()
        df["month"] = np.where(m.str.isdigit(), m.map(lambda x: C.MONTHS[int(x) - 1] if x.isdigit() else x), m.str[:3].str.upper())
        df["rainfall"] = pd.to_numeric(df["rainfall"], errors="coerce")
        df = df.pivot_table(index=["state", "district", "year"], columns="month", values="rainfall",
                            aggfunc=lambda x: x.sum(min_count=1)).reset_index()
    for c in C.MONTHS:
        if c not in df.columns:
            df[c] = np.nan
    if "annual" not in df.columns:
        df["annual"] = np.nan
    df = df[["state", "district", "year"] + C.MONTHS + ["annual"]].copy()
    log["rain_rows_raw"] = len(df)
    for c in ["year"] + C.MONTHS + ["annual"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["state", "district", "year"])
    df["state"], df["district"], df["year"] = clean_name(df["state"]), clean_name(df["district"]), df["year"].astype(int)
    df[C.MONTHS + ["annual"]] = df[C.MONTHS + ["annual"]].where(df[C.MONTHS + ["annual"]] >= 0)  # negatives -> NaN
    log["rain_missing_monthly_cells"] = int(df[C.MONTHS].isna().sum().sum())
    df = df.groupby(["state", "district", "year"], as_index=False).mean()

    key = ["state", "district", "year"]
    monthly = df.melt(id_vars=key, value_vars=C.MONTHS, var_name="month", value_name="rain").dropna()

    parts = []
    for season, months in C.SEASON_MONTHS.items():
        t = df[key].copy()
        t["season"] = season
        t["season_rain"] = df[[C.MONTHS[m - 1] for m in months]].sum(axis=1, min_count=len(months))
        parts.append(t)
    seasonal = pd.concat(parts).dropna(subset=["season_rain"])
    g = seasonal.groupby(["state", "district", "season"])["season_rain"]
    n, mu, sd = g.transform("count"), g.transform("mean"), g.transform("std")
    ok = (n >= 5) & (sd > 0)
    seasonal["rain_z"] = ((seasonal["season_rain"] - mu) / sd).where(ok)
    seasonal["rain_anom_pct"] = ((seasonal["season_rain"] / mu - 1) * 100).where(ok)

    annual = df[key].copy()
    annual["annual_rain"] = df[C.MONTHS].sum(axis=1, min_count=12).fillna(df["annual"])
    annual = annual.dropna(subset=["annual_rain"])
    log["rain_rows_clean"] = len(df)
    return monthly, seasonal.reset_index(drop=True), annual


# ------------------------------------------------------------------ integration
def integrate(crop, seasonal, annual, monthly, log):
    """Harmonise geography (fuzzy match) then join on state+district+year(+season)."""
    crop = crop.copy()
    sm = _map_names(crop["state"], seasonal["state"], 0.85)
    crop["state"] = crop["state"].map(sm)
    crop = crop.dropna(subset=["state"])
    matched = unmatched = 0
    for st, g in crop.groupby("state"):
        dm = _map_names(g["district"], seasonal.loc[seasonal["state"] == st, "district"], 0.80)
        matched += sum(v is not None for v in dm.values())
        unmatched += sum(v is None for v in dm.values())
        crop.loc[g.index, "district"] = g["district"].map(dm)
    crop = crop.dropna(subset=["district"])
    log["districts_matched"], log["districts_unmatched"] = matched, unmatched

    m = crop.merge(seasonal, on=["state", "district", "year", "season"], how="inner")
    m = m.merge(annual, on=["state", "district", "year"], how="left")
    log["integrated_rows"] = len(m)
    g = m.groupby(["state", "district", "crop", "season"])["yield"]
    n, mu, sd = g.transform("count"), g.transform("mean"), g.transform("std")
    ok = (n >= 5) & (sd > 0)
    m["yield_z"] = ((m["yield"] - mu) / sd).where(ok)
    m["yield_anom_pct"] = ((m["yield"] / mu - 1) * 100).where(ok)

    # keep only geography that exists in the integrated set for the other tables
    keys = m[["state", "district"]].drop_duplicates()
    return m, annual.merge(keys), monthly.merge(keys)


def run_etl(crop_raw, rain_raw):
    log = {}
    crop = clean_crop(crop_raw, log)
    monthly, seasonal, annual = clean_rain(rain_raw, log)
    integ, annual, monthly = integrate(crop, seasonal, annual, monthly, log)
    return integ, annual, monthly, log
