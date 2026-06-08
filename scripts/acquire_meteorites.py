"""Acquire the NASA Meteorite Landings dataset (the auditor's proving ground).

Downloads the public CSV to data/meteorites.csv. `data/` is git-ignored, so this is
how you get the demo dataset after a fresh clone — it is small (~45k rows, a few MB)
and comes from a public mirror. Run:  python scripts/acquire_meteorites.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "data" / "meteorites.csv"

# Public mirror of the NASA / Meteoritical Society "Meteorite Landings" set. Kept in
# sync with METEORITES.source_url in auditor/datasets.py.
SOURCE = (
    "https://raw.githubusercontent.com/pylablanche/Kaggle_Meteorites/"
    "master/meteorite-landings.csv"
)


def main() -> None:
    df = pd.read_csv(SOURCE)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {len(df):,} rows x {df.shape[1]} cols -> {OUT}")


if __name__ == "__main__":
    main()
