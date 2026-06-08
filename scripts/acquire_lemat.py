"""Acquire a tabular sample of LeMaterial/LeMat-Bulk for the auditor.

The full dataset is 5M+ rows with heavy nested-array columns (forces, positions).
We only want the *scalar science columns* that a row-wise auditor can reason about,
so we read just those columns from one remote parquet shard (parquet is columnar,
so HTTP range requests transfer a fraction of the 186 MB shard) and save a
reproducible random sample to data/lemat_bulk_sample.csv.

Throwaway provenance script (Phase A/B). Run:  python scripts/acquire_lemat.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "data" / "lemat_bulk_sample.csv"

_BASE = "https://huggingface.co/api/datasets/LeMaterial/LeMat-Bulk/parquet"

# Sample ACROSS configs, not just the cleanest one. `functional` then varies,
# `cross_compatibility` flips, and the messy `non_compatible` split (dos_ef ~98%
# null, magnetization ~19% null) contributes real schema-check signal. The naive
# single-config sample looked deceptively clean — this is the bake-off lesson.
SHARDS = {
    "compatible_pbe": (f"{_BASE}/compatible_pbe/train/0.parquet", 8_000),
    "compatible_pbesol": (f"{_BASE}/compatible_pbesol/train/0.parquet", 4_000),
    "compatible_scan": (f"{_BASE}/compatible_scan/train/0.parquet", 4_000),
    "non_compatible": (f"{_BASE}/non_compatible/train/0.parquet", 9_000),
}

# Scalar (+ small list) science columns worth auditing. We deliberately omit the
# big per-atom arrays (forces, cartesian_site_positions, lattice_vectors, ...).
COLUMNS = [
    "immutable_id",                  # provenance id: mp-*, oqmd-*, agm-* (source DB)
    "chemical_formula_descriptive",  # three formula representations that must agree
    "chemical_formula_reduced",
    "chemical_formula_anonymous",
    "elements",                      # list -> stringify
    "nelements",
    "nsites",
    "nperiodic_dimensions",
    "energy",                        # eV
    "total_magnetization",           # has nulls upstream
    "dos_ef",                        # ~11% null upstream
    "functional",                    # categorical: pbe / ...
    "cross_compatibility",
    "entalpic_fingerprint",          # dedup key
    "last_modified",
]

SEED = 0


def main() -> None:
    parts = []
    for cfg, (url, n) in SHARDS.items():
        df = pd.read_parquet(url, columns=COLUMNS, engine="pyarrow")
        part = df.sample(n=min(n, len(df)), random_state=SEED)
        parts.append(part)
        print(f"  {cfg:<20} shard rows {len(df):>8,} -> sampled {len(part):,}")

    sample = pd.concat(parts, ignore_index=True)
    # shuffle so configs are interleaved, not block-ordered
    sample = sample.sample(frac=1.0, random_state=SEED).reset_index(drop=True)

    # stringify list-valued columns so they round-trip through CSV cleanly
    for col in ("elements",):
        if col in sample.columns:
            sample[col] = sample[col].apply(
                lambda x: "-".join(map(str, x)) if x is not None else None
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(OUT, index=False)
    print(f"wrote {len(sample):,} rows x {sample.shape[1]} cols -> {OUT}")


if __name__ == "__main__":
    main()
