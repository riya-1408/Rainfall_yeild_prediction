# AgriRain Analytics – Rainfall vs Crop Production in India, with Machine-Learning Yield Prediction

Ingests district-wise **crop production** and **rainfall** data (schema of the Government of India **data.gov.in**
datasets), cleans and integrates it, analyses the rainfall–yield relationship, **predicts crop yield with machine
learning**, and serves an interactive web dashboard.

## Quick start
```bash
pip install -r requirements.txt
python run_pipeline.py        # clean → integrate → analytics → machine learning → frontend/data.js
python serve.py               # opens http://localhost:8000   (or just double-click frontend/index.html)
```
The dashboard is plain HTML/CSS/JS (no internet, Node or build step needed).

## Pipeline
```
raw CSV → clean → integrate (geo-harmonise + join + anomalies) → analytics + ML → frontend/data.js → dashboard
```
| Stage | What it does | Code |
|---|---|---|
| Clean / integrate | standardise headers, validate, remove duplicates and outliers, fuzzy-match district names, join crop and rainfall data | `src/etl.py` |
| Analytics | rainfall & yield anomalies, Pearson/Spearman correlation, extreme-year impact, rainfall trends, per-district rain–yield sensitivity | `src/analysis.py` |
| **Machine learning** | yield prediction with a prediction range and a Low / Normal / High outcome | `src/ml.py` |

## Machine learning – yield prediction
**What it predicts:** the yield (t/ha) of a district-crop for **any year from 2016 up to 15 years ahead**, and any season
rainfall you type in, with an 80 % prediction range, the expected production, and the probability of a Low / Normal / High
outcome. Further-out years get a wider range, since a back-test of how the error grows with distance from the data is used
to widen it.

**Algorithm – Random Forest Regression** (`sklearn.ensemble.RandomForestRegressor`), a bagged ensemble of decision trees.
Categorical inputs (crop, season, state) are one-hot encoded; numeric inputs (rainfall z-score and its square, season
rainfall, rainfall anomaly %, annual rainfall, rainfall CV, and a yearly-trend feature) are standardised. The target is
relative yield = yield ÷ that district-crop's historical mean yield, so one forest handles every crop on the same scale.
`n_estimators` and `min_samples_leaf` are tuned with a small grid search on a validation window inside the training years
(the standard train / validation / test workflow) — currently 500 trees, minimum 2 samples per leaf. It is compared
against a plain Linear Regression on the same features.

**Honest evaluation**
* Time-based split: train on the earlier years, test on the latest years the model has never seen.
* The model is *chosen* on a validation window inside the training years – never on the test years.
* Climatology and historical means come from training years only (no leakage).
* The 80 % range is calibrated without the test years and then checked against them (coverage is reported).
* The Low / Normal / High outcome is derived from the same model and its error distribution, so it can never contradict the numeric prediction.

**Result on the bundled sample data (test years 2012–2015):** error (MAPE) 6.51 % vs 6.97 % for the
Linear Regression baseline; R² 0.54; the 80 % range contained the true yield for 79.2 % of unseen records; outcome
accuracy 72 % vs 43 % baseline. Feature importance from the forest itself: rainfall anomaly (z-score) matters most, followed by the yearly
trend, then the rainfall anomaly in %. The test years lie up to 4 years beyond the training years, so predicting the nearer forecast years
is easier than this test; the prediction range widens for years further out to reflect that — a Random Forest cannot extrapolate a linear
trend as cleanly as a regression model, so for far-future years the point prediction levels off while the (honestly wider) range carries
more of the information.

**How exact values are produced:** for every district-crop and every forecast year the fitted model is evaluated on a fine rainfall grid
(−3σ … +3σ in 0.1σ steps) and the dashboard interpolates between grid points, so any rainfall value and year you pick gets a prediction.
Checked against calling the model directly, the largest difference was 0.013 %.

Outputs: `outputs/ml_regression_metrics.csv`, `ml_classification_metrics.csv`, `ml_feature_importance.csv`, `ml_test_predictions.csv` (with prediction ranges).

## Dashboard (`frontend/`)
Tabs: **Overview** · **Crop production** · **Rainfall** · **Districts** · **Prediction**.
* **Prediction tab:** choose state, district, crop and **forecast year** (2016–2030); *type* the season rainfall (mm) and cropped area
  (ha) → predicted yield, 80 % range, expected production, change vs the long-run average, likely outcome with probabilities, the model's
  top feature-importance drivers. (The prediction chart was removed; the page is numbers only.)
* Filters (state, crop, season, year range) on the other tabs now apply **immediately** when you change a dropdown. On the **Rainfall** tab,
  choosing a crop and/or season switches the charts to *season* rainfall (e.g. Kharif = Jun–Sep) averaged over the districts that grow that crop. Light/dark mode. Charts are hand-built SVG (no libraries).

## Using real data
1. From data.gov.in download district-wise crop production and district-wise (monthly) rainfall CSVs.
2. Save as `data/raw/crop_production.csv` and `data/raw/district_rainfall.csv`; delete `data/raw/SAMPLE_DATA.txt`.
3. Expected columns (case-insensitive; more aliases in `src/config.py`): crop `State_Name, District_Name, Crop_Year, Season, Crop, Area, Production`; rainfall `STATE, DISTRICT, YEAR, JAN…DEC` (or long `Month`+`Rainfall`).
4. Run `python run_pipeline.py`. All ML results and the dashboard update automatically; the best model is re-selected on the new data.

## Note on the bundled data
`data/raw/*.csv` is a **synthetic sample** with the same columns as data.gov.in (generated by `src/generate_sample_data.py`, deliberately dirty).
Its rainfall→yield relationship and yearly trend are built in, so the reported accuracies demonstrate the method; the sample has ~7 % random noise,
which limits any model to roughly 5.6 % error — Random Forest (6.51 %) is close to that ceiling. Re-run on real data before drawing agricultural conclusions.
