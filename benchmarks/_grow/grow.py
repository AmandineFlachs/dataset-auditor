"""Grow the held-out `test` split of the two element benchmarks, disciplined.

Metadata (symbol/atomic_number/period), id scheme, class balance and the natural/planted
pairing are correct BY CONSTRUCTION from REFERENCE below. The only human/agent judgement is
the chemistry ground truth (STP phase / metal-class), which is adversarially verified before
--append is run.

Disjointness is guaranteed *programmatically*: the selector loads the existing case IDs from
ALL splits (the same files assert_disjoint_splits reads in CI) and only emits element/value
pairs whose IDs are free. It reasons over IDs only -- never over test labels -- so the
held-out answers are never inspected. Output prints only the newly chosen elements + balance.

    python benchmarks/_grow/grow.py            # write candidate files under _grow/
    python benchmarks/_grow/grow.py --append   # append candidates to the real test.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
SPLITS = ("dev", "calibration", "test")
TARGET_PAIRS = 20  # 20 natural(plausible) + 20 planted(implausible) = 40 new held-out cases

# element -> (symbol, atomic_number, period, stp_phase, classification)
# Broad pool of elements with defensible, unambiguous ground truth. Deliberately EXCLUDES
# near-room-temperature melters whose STP phase is contestable (Ga 29.8 C, Cs 28.5 C) and
# radioactive-only / ill-defined elements. The selector picks whichever pairs are still free.
REFERENCE = {
    "Hydrogen": ("H", 1, 1, "gas", "nonmetal"),
    "Helium": ("He", 2, 1, "gas", "nonmetal"),
    "Lithium": ("Li", 3, 2, "solid", "metal"),
    "Beryllium": ("Be", 4, 2, "solid", "metal"),
    "Boron": ("B", 5, 2, "solid", "metalloid"),
    "Carbon": ("C", 6, 2, "solid", "nonmetal"),
    "Nitrogen": ("N", 7, 2, "gas", "nonmetal"),
    "Oxygen": ("O", 8, 2, "gas", "nonmetal"),
    "Fluorine": ("F", 9, 2, "gas", "nonmetal"),
    "Neon": ("Ne", 10, 2, "gas", "nonmetal"),
    "Sodium": ("Na", 11, 3, "solid", "metal"),
    "Magnesium": ("Mg", 12, 3, "solid", "metal"),
    "Aluminium": ("Al", 13, 3, "solid", "metal"),
    "Silicon": ("Si", 14, 3, "solid", "metalloid"),
    "Phosphorus": ("P", 15, 3, "solid", "nonmetal"),
    "Sulfur": ("S", 16, 3, "solid", "nonmetal"),
    "Chlorine": ("Cl", 17, 3, "gas", "nonmetal"),
    "Argon": ("Ar", 18, 3, "gas", "nonmetal"),
    "Potassium": ("K", 19, 4, "solid", "metal"),
    "Calcium": ("Ca", 20, 4, "solid", "metal"),
    "Scandium": ("Sc", 21, 4, "solid", "metal"),
    "Titanium": ("Ti", 22, 4, "solid", "metal"),
    "Vanadium": ("V", 23, 4, "solid", "metal"),
    "Chromium": ("Cr", 24, 4, "solid", "metal"),
    "Manganese": ("Mn", 25, 4, "solid", "metal"),
    "Iron": ("Fe", 26, 4, "solid", "metal"),
    "Cobalt": ("Co", 27, 4, "solid", "metal"),
    "Nickel": ("Ni", 28, 4, "solid", "metal"),
    "Copper": ("Cu", 29, 4, "solid", "metal"),
    "Zinc": ("Zn", 30, 4, "solid", "metal"),
    "Germanium": ("Ge", 32, 4, "solid", "metalloid"),
    "Arsenic": ("As", 33, 4, "solid", "metalloid"),
    "Selenium": ("Se", 34, 4, "solid", "nonmetal"),
    "Bromine": ("Br", 35, 4, "liquid", "nonmetal"),
    "Krypton": ("Kr", 36, 4, "gas", "nonmetal"),
    "Rubidium": ("Rb", 37, 5, "solid", "metal"),
    "Strontium": ("Sr", 38, 5, "solid", "metal"),
    "Yttrium": ("Y", 39, 5, "solid", "metal"),
    "Zirconium": ("Zr", 40, 5, "solid", "metal"),
    "Niobium": ("Nb", 41, 5, "solid", "metal"),
    "Molybdenum": ("Mo", 42, 5, "solid", "metal"),
    "Ruthenium": ("Ru", 44, 5, "solid", "metal"),
    "Rhodium": ("Rh", 45, 5, "solid", "metal"),
    "Palladium": ("Pd", 46, 5, "solid", "metal"),
    "Silver": ("Ag", 47, 5, "solid", "metal"),
    "Cadmium": ("Cd", 48, 5, "solid", "metal"),
    "Indium": ("In", 49, 5, "solid", "metal"),
    "Tin": ("Sn", 50, 5, "solid", "metal"),
    "Antimony": ("Sb", 51, 5, "solid", "metalloid"),
    "Tellurium": ("Te", 52, 5, "solid", "metalloid"),
    "Iodine": ("I", 53, 5, "solid", "nonmetal"),
    "Xenon": ("Xe", 54, 5, "gas", "nonmetal"),
    "Barium": ("Ba", 56, 6, "solid", "metal"),
    "Cerium": ("Ce", 58, 6, "solid", "metal"),
    "Neodymium": ("Nd", 60, 6, "solid", "metal"),
    "Hafnium": ("Hf", 72, 6, "solid", "metal"),
    "Tantalum": ("Ta", 73, 6, "solid", "metal"),
    "Tungsten": ("W", 74, 6, "solid", "metal"),
    "Rhenium": ("Re", 75, 6, "solid", "metal"),
    "Osmium": ("Os", 76, 6, "solid", "metal"),
    "Iridium": ("Ir", 77, 6, "solid", "metal"),
    "Platinum": ("Pt", 78, 6, "solid", "metal"),
    "Gold": ("Au", 79, 6, "solid", "metal"),
    "Mercury": ("Hg", 80, 6, "liquid", "metal"),
    "Thallium": ("Tl", 81, 6, "solid", "metal"),
    "Lead": ("Pb", 82, 6, "solid", "metal"),
    "Bismuth": ("Bi", 83, 6, "solid", "metal"),
    "Radon": ("Rn", 86, 6, "gas", "nonmetal"),
}

DOMAINS = {  # domain key -> (task dir, truth-field index in REFERENCE tuple, allowed values)
    "labels": ("labels_plausibility", 3, ("solid", "liquid", "gas")),
    "class": ("element_classification", 4, ("metal", "nonmetal", "metalloid")),
}


def existing_ids(task: str) -> set[str]:
    """IDs already used across ALL splits of a task. Reads only the 'id' field."""
    ids: set[str] = set()
    for split in SPLITS:
        path = BENCH / task / f"{split}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            obj = json.loads(line)
            if isinstance(obj, dict) and "id" in obj:
                ids.add(obj["id"])
    return ids


def _ctx(element: str) -> dict:
    sym, z, period, _phase, _cls = REFERENCE[element]
    return {"element": element, "symbol": sym, "atomic_number": z, "period": period}


def select(domain: str) -> list[dict]:
    """Pick the first TARGET_PAIRS elements (by Z) whose natural+planted IDs are both free."""
    task, truth_idx, allowed = DOMAINS[domain]
    used = existing_ids(task)
    chosen: list[dict] = []
    picked_elements: list[str] = []
    for i, (el, ref) in enumerate(sorted(REFERENCE.items(), key=lambda kv: kv[1][1])):
        if len(chosen) >= TARGET_PAIRS * 2:
            break
        true = ref[truth_idx]
        slug = el.lower()
        nat_id = f"{slug}-{true}"
        if nat_id in used:
            continue
        wrong_opts = [v for v in allowed if v != true]
        wrong_opts = wrong_opts[i % len(wrong_opts):] + wrong_opts[: i % len(wrong_opts)]  # vary
        wrong = next((w for w in wrong_opts if f"{slug}-{w}" not in used), None)
        if wrong is None:
            continue
        kind = "phase at STP" if domain == "labels" else "classification"
        chosen.append({"id": nat_id, "value": true, "context": _ctx(el),
                       "expected": "plausible", "origin": "natural",
                       "note": f"{el} ({ref[0]}) is {true} ({kind})"})
        chosen.append({"id": f"{slug}-{wrong}", "value": wrong, "context": _ctx(el),
                       "expected": "implausible", "origin": "planted",
                       "note": f"planted: {el} is {true}, not {wrong}"})
        picked_elements.append(el)
    if len(chosen) < TARGET_PAIRS * 2:
        raise SystemExit(f"{domain}: only found {len(chosen)//2}/{TARGET_PAIRS} free pairs; widen REFERENCE")
    return chosen, picked_elements


def _summary(cases: list[dict]) -> str:
    plaus = sum(1 for c in cases if c["expected"] == "plausible")
    vals: dict = {}
    for c in cases:
        vals[c["value"]] = vals.get(c["value"], 0) + 1
    return f"N={len(cases)}  plausible={plaus}  implausible={len(cases) - plaus}  values={vals}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--append", action="store_true")
    args = ap.parse_args()
    for domain, (task, _ti, _al) in DOMAINS.items():
        cases, elements = select(domain)
        print(f"[{domain} -> {task}] {_summary(cases)}")
        print(f"  new elements: {', '.join(elements)}")
        (HERE / f"{domain}_candidates.jsonl").write_text(
            "\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
        if args.append:
            dest = BENCH / task / "test.jsonl"
            with dest.open("a", encoding="utf-8") as fh:  # append-only; never read back
                for c in cases:
                    fh.write(json.dumps(c) + "\n")
            print(f"  appended {len(cases)} cases to test.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
