"""Machine-learning layer: yield PREDICTION for any year, using RANDOM FOREST REGRESSION.

  * Predicts the yield (t/ha) of a district-crop-season for a chosen YEAR and season rainfall.
  * Every prediction comes with an 80 % prediction range and a Low / Normal / High outcome with probabilities.

Method
------
Algorithm   Random Forest Regression (bagged ensemble of decision trees, scikit-learn RandomForestRegressor).
            Categorical features (crop, season, state) are one-hot encoded; numeric features (rainfall z-score
            and its square, season rainfall, rainfall anomaly %, annual rainfall, rainfall CV, and a yearly-trend
            feature) are standardised. The target is relative yield = yield / that district-crop's historical
            mean yield, so one forest handles every crop on the same 0-2-ish scale.
Tuning      n_estimators and min_samples_leaf are tuned with a small grid search on a validation window INSIDE
            the training years (never on the test years) - the standard train / validation / test workflow.
Honest test Time-based split: train on the earlier years, test on the latest unseen years. All climatology and
            historical means are computed from the training years only (no leakage).
Comparison  Compared against a plain Linear Regression on the same features, to show the forest is
            actually earning its keep.
Uncertainty The out-of-sample error of the forest (log scale, per crop) gives the prediction range. The range
            WIDENS with the forecast horizon based on how much error back-tests show growing with distance from
            the data. Outcome probabilities come from the same error distribution, so the numeric prediction and
            the outcome label never contradict each other.
Forecast    The forest is refit on ALL years and predicts every year from the first year after the data up to
            YEARS_AHEAD years ahead, over a fine rainfall grid (-3 sigma .. +3 sigma in 0.1 sigma steps). The
            dashboard interpolates the grid for any rainfall value and any year the user picks. Random Forests
            cannot extrapolate a trend past what they were trained on as cleanly as a linear model, so far-future
            forecasts lean more on the (honestly) wider prediction range than on the point prediction alone.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import f1_score, mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

GK = ["state", "district", "crop", "season"]
CATS = ["crop", "season", "state"]
NUMS = ["rain_z", "rain_z_sq", "season_rain", "rain_anom_pct_f", "annual_rain", "rain_cv", "yr_c"]
LOW, HIGH = 0.90, 1.10                      # outcome classes on relative yield: <90 % Low, >110 % High
CLASSES = ["Low", "Normal", "High"]
PI_LEVEL, PI_Z = 0.80, 1.2816               # 80 % prediction range
Z_GRID = [round(z, 1) for z in np.arange(-3.0, 3.001, 0.1)]
YEARS_AHEAD = 15                            # forecast years offered in the dashboard
TESTED_HORIZON = 4                          # the test window reaches this many years beyond the training data
GRID_N_ESTIMATORS = [200, 500]              # small hyperparameter grid, tuned on the validation years
GRID_MIN_LEAF = [2, 3, 5]
MIN_HIST = 5                                # a district-crop needs >= 5 training years to be modelled


# ------------------------------------------------------------------ features
def baselines(df, years):
    """Rainfall climatology, historical mean yield and history mid-year, computed from `years` only."""
    d = df[df["year"].isin(years)]
    rain = d.drop_duplicates(["state", "district", "season", "year"])
    clim = rain.groupby(["state", "district", "season"])["season_rain"].agg(
        rain_mean="mean", rain_std="std", rain_min="min", rain_max="max").reset_index()
    ann = d.drop_duplicates(["state", "district", "year"]).groupby(["state", "district"])["annual_rain"].agg(
        ann_mean="mean", ann_std="std").reset_index()
    ann["rain_cv"] = ann["ann_std"] / ann["ann_mean"]
    hist = d.groupby(GK).agg(hist_mean=("yield", "mean"), n_years=("yield", "count"), center_year=("year", "mean")).reset_index()
    return dict(clim=clim, ann=ann[["state", "district", "ann_mean", "rain_cv"]], hist=hist[hist["n_years"] >= MIN_HIST])


def add_rain_features(f):
    f["rain_z"] = (f["season_rain"] - f["rain_mean"]) / f["rain_std"]
    f["rain_z_sq"] = f["rain_z"] ** 2
    f["rain_anom_pct_f"] = (f["season_rain"] / f["rain_mean"] - 1) * 100
    f["yr_c"] = f["year"] - f["center_year"]
    return f


def featurize(df, base):
    f = (df.merge(base["clim"], on=["state", "district", "season"]).merge(base["ann"], on=["state", "district"])
           .merge(base["hist"], on=GK))
    f = add_rain_features(f[f["rain_std"] > 0].copy())
    f["ratio"] = f["yield"] / f["hist_mean"]
    f["cls"] = np.where(f["ratio"] < LOW, "Low", np.where(f["ratio"] > HIGH, "High", "Normal"))
    return f.reset_index(drop=True)


# ------------------------------------------------------------------ models
class RandomForestModel:
    """Random Forest Regression on relative yield: one-hot categoricals + standardised rainfall/trend features."""
    name = "Random Forest Regression"

    def __init__(self, n_estimators=300, min_samples_leaf=3):
        self.n_estimators, self.min_samples_leaf = n_estimators, min_samples_leaf

    def fit(self, f):
        pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATS),
                                 ("num", StandardScaler(), NUMS)])
        self.est = RandomForestRegressor(n_estimators=self.n_estimators, min_samples_leaf=self.min_samples_leaf,
                                          random_state=42, n_jobs=1)
        self.pipe = Pipeline([("pre", pre), ("m", self.est)]).fit(f[CATS + NUMS], f["ratio"])
        return self

    def predict(self, f):
        return np.clip(self.pipe.predict(f[CATS + NUMS]), 0.05, None)

    def feature_importance(self, top=8):
        names = list(self.pipe.named_steps["pre"].get_feature_names_out())
        imp = self.est.feature_importances_
        order = np.argsort(imp)[::-1][:top]
        return [(names[i].split("__", 1)[-1], round(float(imp[i]), 3)) for i in order]


class LinearBaseline:
    """Plain Linear Regression on the same features - a simple point of comparison for the report."""
    name = "Linear Regression (baseline)"

    def fit(self, f):
        pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATS),
                                 ("num", StandardScaler(), NUMS)])
        self.pipe = Pipeline([("pre", pre), ("m", LinearRegression())]).fit(f[CATS + NUMS], f["ratio"])
        return self

    def predict(self, f):
        return np.clip(self.pipe.predict(f[CATS + NUMS]), 0.05, None)


def tune_random_forest(fit_df, val_df):
    """Small grid search for n_estimators / min_samples_leaf on a validation window inside the training years."""
    best = None
    for leaf in GRID_MIN_LEAF:
        for n in GRID_N_ESTIMATORS:
            m = RandomForestModel(n, leaf).fit(fit_df)
            mape = _metrics("", m.predict(val_df), val_df)["mape"]
            if best is None or mape < best[0]:
                best = (mape, n, leaf)
    return best[1], best[2]


# ------------------------------------------------------------------ evaluation helpers
def _metrics(name, ratio_pred, ev):
    yp = ratio_pred * ev["hist_mean"].values
    return dict(model=name, r2=float(r2_score(ev["ratio"], ratio_pred)),
                mape=float(np.mean(np.abs(yp - ev["yield"].values) / ev["yield"].values) * 100),
                mae=float(mean_absolute_error(ev["yield"], yp)))


def sigma_by_crop(crop_col, log_resid, min_n=40):
    """Std-dev of the log-error per crop (falls back to the pooled value for crops with few residuals)."""
    pooled = float(np.std(log_resid))
    s = pd.Series(log_resid).groupby(np.asarray(crop_col)).agg(["std", "count"])
    return {c: float(r["std"]) if r["count"] >= min_n else pooled for c, r in s.iterrows()}, pooled


def horizon_k(res, h):
    """How fast the error variance grows with the forecast horizon h (1 = first year after the data):
    var(h) = var(1) * (1 + k * (h - 1)).  Estimated from back-tests, never negative."""
    hs = np.unique(h)
    if len(hs) < 2:
        return 0.0
    var = np.array([np.mean(res[h == x] ** 2) for x in hs])
    b, a = np.polyfit(hs - 1, var, 1)
    return float(max(b / a, 0.0)) if a > 0 else 0.0


def outcome_probs(log_ratio_pred, sigma):
    p_low = norm.cdf((np.log(LOW) - log_ratio_pred) / sigma)
    p_high = 1 - norm.cdf((np.log(HIGH) - log_ratio_pred) / sigma)
    return np.c_[p_low, np.clip(1 - p_low - p_high, 0, 1), p_high]


# ------------------------------------------------------------------ main
def run_ml(integ):
    df = integ.dropna(subset=["season_rain", "annual_rain", "yield"]).copy()
    df = df[df["yield"] > 0]
    years = sorted(df["year"].unique())
    n_test = max(3, round(0.25 * len(years)))
    tr_years, te_years = years[:-n_test], years[-n_test:]
    n_val = max(2, min(3, len(tr_years) // 4))
    fit_years, val_years = tr_years[:-n_val], tr_years[-n_val:]

    # 1) hyperparameter tuning on a validation window INSIDE the training years (never on the test years)
    f_fit = featurize(df, baselines(df, fit_years))
    fit_df, val_df = f_fit[f_fit["year"].isin(fit_years)], f_fit[f_fit["year"].isin(val_years)]
    n_estimators, min_leaf = tune_random_forest(fit_df, val_df)

    # 2) honest evaluation on the unseen test years (fit on ALL training years with the tuned hyperparameters)
    f_tr = featurize(df, baselines(df, tr_years))
    tr, te = f_tr[f_tr["year"].isin(tr_years)], f_tr[f_tr["year"].isin(te_years)]
    rf = RandomForestModel(n_estimators, min_leaf).fit(tr)
    lin = LinearBaseline().fit(tr)
    p_rf, p_lin = rf.predict(te), lin.predict(te)
    lin_row = _metrics(lin.name, p_lin, te)
    rf_row = {**_metrics(rf.name, p_rf, te), "selected": True,
              "params": f"n_estimators={n_estimators}, min_samples_leaf={min_leaf} (tuned on validation years)"}
    reg_rows = [lin_row, rf_row]
    importance = rf.feature_importance()

    # 3) prediction range: log-errors of the forest on out-of-sample years, and how they grow with the horizon
    #    (must use a model trained on fit_years ONLY - `rf` above was trained on tr_years, which already includes
    #    val_years, so reusing it here would score the forest on rows it has already seen)
    rf_v = RandomForestModel(n_estimators, min_leaf).fit(fit_df)
    p_val = rf_v.predict(val_df)
    res_v = np.log(val_df["ratio"].values) - np.log(p_val)
    res_t = np.log(te["ratio"].values) - np.log(p_rf)
    h_v, h_t = val_df["year"].values - fit_years[-1], te["year"].values - tr_years[-1]
    k_v = horizon_k(res_v, h_v)
    sig_v, pool_v = sigma_by_crop(val_df["crop"], res_v / np.sqrt(1 + k_v * (h_v - 1)))      # calibrated WITHOUT the test years ...
    s_te = te["crop"].map(lambda c: sig_v.get(c, pool_v)).values * np.sqrt(1 + k_v * (h_t - 1))
    lo_t, hi_t = p_rf * np.exp(-PI_Z * s_te), p_rf * np.exp(PI_Z * s_te)
    coverage = float(((te["ratio"].values >= lo_t) & (te["ratio"].values <= hi_t)).mean())   # ... so this is honest
    res_all, h_all, crop_all = np.r_[res_v, res_t], np.r_[h_v, h_t], np.r_[val_df["crop"].values, te["crop"].values]
    k_all = horizon_k(res_all, h_all)                                                        # used for the forecast
    sig_all, pool_all = sigma_by_crop(crop_all, res_all / np.sqrt(1 + k_all * (h_all - 1)))

    # 4) Low / Normal / High outcome derived from the same model + error distribution
    P = outcome_probs(np.log(p_rf), s_te)
    pred_cls = np.array(CLASSES)[P.argmax(1)]
    clf_rows = [dict(model=f"{rf.name} → outcome", accuracy=float((pred_cls == te["cls"].values).mean()),
                     macro_f1=float(f1_score(te["cls"], pred_cls, average="macro", labels=CLASSES, zero_division=0)))]

    te = te.assign(pred_ratio=p_rf, pred_yield=p_rf * te["hist_mean"].values, lo=lo_t * te["hist_mean"].values,
                   hi=hi_t * te["hist_mean"].values, pred_class=pred_cls)

    # 5) refit on ALL years -> forecast every year from the first year after the data over a rainfall grid
    fb = baselines(df, years)
    ff = featurize(df, fb)
    final = RandomForestModel(n_estimators, min_leaf).fit(ff)
    last = int(years[-1])
    fyears = list(range(last + 1, last + 1 + YEARS_AHEAD))
    area = df.sort_values("year").groupby(GK).tail(3).groupby(GK)["area"].mean().rename("area").reset_index()
    combos = fb["hist"].merge(fb["clim"], on=["state", "district", "season"]).merge(fb["ann"], on=["state", "district"]).merge(area, on=GK)
    combos = combos[combos["rain_std"] > 0].reset_index(drop=True)
    big = combos.merge(pd.DataFrame({"year": fyears}), how="cross").merge(pd.DataFrame({"zg": Z_GRID}), how="cross")
    big["season_rain"] = (big["rain_mean"] + big["zg"] * big["rain_std"]).clip(lower=0)
    big["annual_rain"] = (big["ann_mean"] + big["season_rain"] - big["rain_mean"]).clip(lower=0)
    big = add_rain_features(big)
    big["pred_yield"] = final.predict(big) * big["hist_mean"]
    big = big.sort_values(GK + ["year", "zg"]).reset_index(drop=True)

    out_combos = []
    for (s, d, c, se), g in big.groupby(GK, sort=False):
        r0 = g.iloc[0]
        grid = g["pred_yield"].values.reshape(len(fyears), len(Z_GRID))          # [year][rainfall step]
        out_combos.append(dict(key=f"{s}|{d}|{c}|{se}", state=s, district=d, crop=c, season=se, base=float(r0["hist_mean"]),
                               area=float(r0["area"]), rain_mean=float(r0["rain_mean"]), rain_std=float(r0["rain_std"]),
                               rain_min=float(r0["rain_min"]), rain_max=float(r0["rain_max"]),
                               sigma=sig_all.get(c, pool_all), grid=np.round(grid, 4).tolist()))
    return dict(
        meta=dict(train_years=[int(tr_years[0]), int(tr_years[-1])], test_years=[int(te_years[0]), int(te_years[-1])],
                  val_years=[int(val_years[0]), int(val_years[-1])], last_data_year=last, years=fyears, forecast_year=fyears[0],
                  n_train=len(tr), n_test=len(te), best=rf.name, n_estimators=n_estimators, min_samples_leaf=min_leaf,
                  low=LOW, high=HIGH, pi_level=PI_LEVEL, pi_z=PI_Z, coverage=coverage, horizon_k=k_all, tested_horizon=TESTED_HORIZON,
                  z_grid=[Z_GRID[0], Z_GRID[-1], round(Z_GRID[1] - Z_GRID[0], 3)], sigma_pooled=pool_all, importance=importance),
        regression=reg_rows, classification=clf_rows, combos=out_combos,
        test_predictions=te[["state", "district", "crop", "season", "year", "yield", "pred_yield", "lo", "hi", "cls", "pred_class"]],
    )
