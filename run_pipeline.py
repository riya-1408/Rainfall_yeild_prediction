"""Analytics + machine-learning pipeline:  python run_pipeline.py [--sample]

 raw CSV --clean--> standardised tables --integrate (geo-harmonise + join + anomalies)--> integrated dataset
      --> analytics (correlation, extreme years, rainfall trends)  --> outputs/*.csv
      --> machine learning (yield prediction, prediction range, outcome, next-year forecast) --> outputs/*.csv
      --> frontend/data.js (dashboard)
"""
import argparse
import time

import pandas as pd

from src import config as C
from src import generate_sample_data
from src.analysis import run_analysis
from src.etl import clean_crop, clean_rain, integrate
from src.export_frontend import build
from src.ml import run_ml


def is_sample():
    m = C.RAW / "SAMPLE_DATA.txt"
    return m.exists() and C.CROP_FILE.stat().st_mtime <= m.stat().st_mtime + 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="(re)generate synthetic sample data first")
    a = ap.parse_args()
    if a.sample or not (C.CROP_FILE.exists() and C.RAIN_FILE.exists()):
        print("Generating synthetic sample data ...")
        generate_sample_data.main()
    C.OUT.mkdir(exist_ok=True)
    t0, log = time.perf_counter(), {}

    print("[1/4] CLEAN      standardise + validate crop and rainfall data")
    crop = clean_crop(pd.read_csv(C.CROP_FILE, dtype=str), log)
    monthly, seasonal, annual = clean_rain(pd.read_csv(C.RAIN_FILE, dtype=str), log)

    print("[2/4] INTEGRATE  geo-harmonise + join + anomalies")
    integ, annual, monthly = integrate(crop, seasonal, annual, monthly, log)

    print("[3/4] ANALYTICS  cube, correlations, extreme years, rainfall trends")
    g = integ.groupby(["state", "crop", "season", "year"]).agg(p=("production", "sum"), a=("area", "sum"), n=("crop", "size"))
    cube = {k: [float(r.p), float(r.a), int(r.n)] for k, r in zip(g.index, g.itertuples(index=False))}
    d = integ.dropna(subset=["rain_z", "yield_z"])
    overall_r = float(d["rain_z"].corr(d["yield_z"]))
    res = run_analysis(integ, annual)
    for name, df in res.items():
        if isinstance(df, pd.DataFrame):
            df.to_csv(C.OUT / f"{name}.csv", index=False)

    print("[4/4] MACHINE LEARNING  yield prediction + prediction range + outcome + next-year forecast")
    ml = run_ml(integ)
    m = ml["meta"]
    pd.DataFrame(ml["regression"]).to_csv(C.OUT / "ml_regression_metrics.csv", index=False)
    pd.DataFrame(ml["classification"]).to_csv(C.OUT / "ml_classification_metrics.csv", index=False)
    pd.DataFrame(ml["meta"]["importance"], columns=["feature", "importance"]).to_csv(C.OUT / "ml_feature_importance.csv", index=False)
    ml["test_predictions"].to_csv(C.OUT / "ml_test_predictions.csv", index=False)
    build(integ, annual, monthly, res, cube, overall_r, ml, is_sample())

    print(f"\nCleaning: {log['crop_rows_raw']:,} raw crop rows -> {log['crop_rows_clean']:,} clean -> {log['integrated_rows']:,} integrated rows")
    print(f"Overall rain-yield r = {overall_r:.3f}")
    print(f"\nML  train {m['train_years'][0]}-{m['train_years'][1]} ({m['n_train']} rows) | validation {m['val_years'][0]}-{m['val_years'][1]} "
          f"| test {m['test_years'][0]}-{m['test_years'][1]} ({m['n_test']} rows, never seen in training)")
    for r in ml["regression"]:
        tag = "  <- " + r["params"] if r.get("selected") else ""
        print(f"  {r['model']:34s} R2={r['r2']:6.3f}  MAPE={r['mape']:5.2f}%  MAE={r['mae']:.3f} t/ha{tag}")
    for r in ml["classification"]:
        print(f"  outcome  {r['model']:44s} accuracy={r['accuracy'] * 100:5.1f}%  macro-F1={r['macro_f1']:.3f}")
    print(f"  {int(m['pi_level'] * 100)}% prediction range contained the true yield for {m['coverage'] * 100:.1f}% of unseen test records")
    print(f"  error variance growth per forecast year: k = {m['horizon_k']:.3f}")
    print(f"  feature importance (Random Forest): {', '.join(f'{n}={v}' for n, v in m['importance'][:5])}")
    print(f"  forecast years: {m['years'][0]}-{m['years'][-1]}  ({len(ml['combos'])} district-crop combinations)")
    print(f"\nTotal time {time.perf_counter() - t0:.1f}s.  Open frontend/index.html (or run: python serve.py)")


if __name__ == "__main__":
    main()
