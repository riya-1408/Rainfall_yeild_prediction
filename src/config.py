"""Central configuration: paths, season definitions, column aliases."""
import calendar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "outputs"
CROP_FILE = RAW / "crop_production.csv"
RAIN_FILE = RAW / "district_rainfall.csv"

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# Calendar months whose rainfall is summed for each agricultural season.
# (Simplification: months are taken from the same calendar year as Crop_Year.)
SEASON_MONTHS = {
    "KHARIF": [6, 7, 8, 9],
    "RABI": [10, 11, 12, 1, 2, 3],
    "SUMMER": [3, 4, 5, 6],
    "AUTUMN": [9, 10, 11],
    "WINTER": [11, 12, 1, 2],
    "WHOLE YEAR": list(range(1, 13)),
}

# Normalised header (lower-case, alphanumerics only) -> canonical column name.
# Extend this if your data.gov.in file uses different headers.
ALIASES = {
    "statename": "state", "state": "state", "stname": "state",
    "districtname": "district", "district": "district", "dist": "district",
    "cropyear": "year", "year": "year",
    "season": "season", "crop": "crop", "cropname": "crop",
    "area": "area", "production": "production",
    "month": "month", "rainfall": "rainfall", "actual": "rainfall",
    "actualrainfall": "rainfall", "annual": "annual",
}
for _i, _m in enumerate(MONTHS, start=1):
    ALIASES[_m.lower()] = _m
    ALIASES[calendar.month_name[_i].lower()] = _m

FRONT = ROOT / "frontend"       # static dashboard (data.js is generated here)
