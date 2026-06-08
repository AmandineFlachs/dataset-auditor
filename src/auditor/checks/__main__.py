"""Run all checks on a dataset and print a summary.

    python -m auditor.checks                     # default: lemat_bulk
    python -m auditor.checks --dataset meteorites
"""

import argparse

from auditor.checks import _summarize, run_all
from auditor.datasets import DATASETS, get
from auditor.load import load

parser = argparse.ArgumentParser(prog="auditor.checks")
parser.add_argument(
    "--dataset",
    default=None,
    choices=sorted(DATASETS),
    help="which dataset to audit (default: lemat_bulk)",
)
args = parser.parse_args()

spec = get(args.dataset)
print(f"auditing dataset: {spec.name}\n")
print(_summarize(run_all(load(spec=spec), spec)))
