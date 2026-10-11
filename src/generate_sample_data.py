"""Generate a SYNTHETIC dataset with the same schema as the data.gov.in files.

Purpose: let the whole system run end-to-end offline / for demos. Replace
data/raw/*.csv with real data.gov.in downloads for real analysis.
The data is intentionally 'dirty' (case/space differences, spelling variants,
missing values, duplicates) so the cleaning stage has real work to do.
"""
import numpy as np
import pandas as pd
from . import config as C

rng = np.random.default_rng(42)
YEARS = list(range(2000, 2016))

# state -> (rain regime, mean annual rain mm, districts)
STATES = {
    "Maharashtra": ("monsoon", 1100, ["Pune", "Nashik", "Ahmednagar", "Solapur", "Nagpur"]),
    "Punjab": ("north", 650, ["Ludhiana", "Amritsar", "Patiala", "Bathinda", "Sangrur"]),
    "Uttar Pradesh": ("monsoon", 900, ["Lucknow", "Kanpur Nagar", "Varanasi", "Agra", "Gorakhpur"]),
    "Karnataka": ("monsoon", 1200, ["Belgaum", "Dharwad", "Mysore", "Bellary", "Raichur"]),
    "Rajasthan": ("monsoon", 480, ["Jaipur", "Jodhpur", "Bikaner", "Kota", "Udaipur"]),
    "West Bengal": ("monsoon", 1700, ["Bardhaman", "Nadia", "Hooghly", "Bankura", "Murshidabad"]),
    "Tamil Nadu": ("ne_monsoon", 950, ["Coimbatore", "Madurai", "Thanjavur", "Salem", "Tirunelveli"]),
    "Madhya Pradesh": ("monsoon", 1050, ["Bhopal", "Indore", "Jabalpur", "Sagar", "Gwalior"]),
}
PROFILES = {
    "monsoon":    [.01, .01, .01, .01, .03, .15, .27, .25, .16, .06, .03, .01],
    "ne_monsoon": [.02, .01, .02, .05, .07, .05, .08, .09, .11, .22, .22, .06],
    "north":      [.06, .06, .05, .03, .03, .08, .22, .22, .10, .04, .02, .09],
}
# crop, season, base yield (t/ha), rainfall sensitivity, curvature, states grown
CROPS = [
    ("Rice", "KHARIF", 2.5, 0.18, -0.03, ["Punjab", "Uttar Pradesh", "West Bengal", "Tamil Nadu", "Karnataka", "Madhya Pradesh"]),
    ("Maize", "KHARIF", 2.2, 0.10, -0.02, ["Karnataka", "Uttar Pradesh", "Rajasthan", "Madhya Pradesh"]),
    ("Bajra", "KHARIF", 1.2, 0.05, -0.01, ["Rajasthan", "Maharashtra", "Uttar Pradesh"]),
    ("Cotton(lint)", "KHARIF", 0.5, 0.10, -0.04, ["Maharashtra", "Karnataka", "Punjab", "Rajasthan", "Madhya Pradesh"]),
    ("Groundnut", "KHARIF", 1.3, 0.12, -0.03, ["Tamil Nadu", "Karnataka", "Rajasthan", "Maharashtra"]),
    ("Soyabean", "KHARIF", 1.0, 0.14, -0.03, ["Madhya Pradesh", "Maharashtra"]),
    ("Wheat", "RABI", 3.0, 0.05, -0.01, ["Punjab", "Uttar Pradesh", "Madhya Pradesh", "Rajasthan"]),
    ("Gram", "RABI", 1.0, 0.08, -0.02, ["Madhya Pradesh", "Rajasthan", "Maharashtra", "Karnataka", "Uttar Pradesh"]),
    ("Sugarcane", "WHOLE YEAR", 70.0, 0.07, -0.01, ["Maharashtra", "Uttar Pradesh", "Karnataka", "Tamil Nadu"]),
]
IRRIGATED = {"Punjab": 0.25}  # irrigation damps rainfall dependence


def _rainfall():
    rows = []
    for st, (regime, mean_rain, dists) in STATES.items():
        state_year = rng.normal(0, 0.18, len(YEARS))  # shared regional weather signal
        for d in dists:
            base = mean_rain * rng.uniform(0.75, 1.25)
            for i, y in enumerate(YEARS):
                total = base * np.exp(state_year[i] + rng.normal(0, 0.10)) * (1 - 0.002 * i)
                w = np.array(PROFILES[regime]) * rng.uniform(0.7, 1.3, 12)
                rows.append([st, d, y, *(total * w / w.sum())])
    return pd.DataFrame(rows, columns=["state", "district", "year"] + C.MONTHS)


def _crops(rain):
    # season-rainfall z-score per district drives the synthetic yield response
    long = []
    for season, months in C.SEASON_MONTHS.items():
        tmp = rain[["state", "district", "year"]].copy()
        tmp["season"] = season
        tmp["rain"] = rain[[C.MONTHS[m - 1] for m in months]].sum(axis=1)
        tmp["z"] = tmp.groupby(["state", "district"])["rain"].transform(lambda x: (x - x.mean()) / x.std())
        long.append(tmp)
    zt = pd.concat(long).set_index(["state", "district", "year", "season"])["z"]

    recs = []
    for crop, season, by, sens, curv, states in CROPS:
        for st in states:
            for d in STATES[st][2]:
                if rng.random() < 0.15:
                    continue  # not every district grows every crop
                dist_eff, base_area = rng.uniform(0.8, 1.2), rng.uniform(5_000, 80_000)
                damp = IRRIGATED.get(st, 1.0)
                for i, y in enumerate(YEARS):
                    z = zt[(st, d, y, season)]
                    yld = by * dist_eff * (1 + 0.012 * i) * np.exp(damp * (sens * z + curv * z * z) + rng.normal(0, 0.07))
                    area = base_area * (1 + 0.01 * i) * rng.uniform(0.9, 1.1)
                    recs.append([st, d.upper(), y, season.title().ljust(11), crop, round(area, 1), round(yld * area, 1)])
    df = pd.DataFrame(recs, columns=["State_Name", "District_Name", "Crop_Year", "Season", "Crop", "Area", "Production"])
    # ---- inject realistic dirt ----
    n = len(df)
    df.loc[rng.choice(n, int(.03 * n), replace=False), "Production"] = np.nan
    df.loc[rng.choice(n, int(.005 * n), replace=False), "Area"] = 0
    return pd.concat([df, df.sample(int(.01 * n), random_state=1)], ignore_index=True)


def main():
    C.RAW.mkdir(parents=True, exist_ok=True)
    rain = _rainfall()
    crop = _crops(rain)
    out = rain.copy()
    out["ANNUAL"] = out[C.MONTHS].sum(axis=1).round(1)
    out[C.MONTHS] = out[C.MONTHS].round(1)
    out["district"] = out["district"].replace({"Ahmednagar": "Ahmadnagar", "Bardhaman": "Barddhaman"})  # spelling variants
    for c in C.MONTHS:  # ~1% missing monthly values
        out.loc[rng.random(len(out)) < 0.01, c] = np.nan
    out = out.rename(columns={"state": "STATE", "district": "DISTRICT", "year": "YEAR"})
    out.to_csv(C.RAIN_FILE, index=False)
    crop.to_csv(C.CROP_FILE, index=False)
    (C.RAW / "SAMPLE_DATA.txt").write_text("Synthetic sample data. Delete this file after replacing the CSVs with real data.gov.in data.")
    print(f"Sample data written: {len(crop):,} crop rows, {len(out):,} rainfall rows -> {C.RAW}")


if __name__ == "__main__":
    main()
