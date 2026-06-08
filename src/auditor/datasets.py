"""Per-dataset configuration — the one place dataset-specific knowledge lives.

Phases 0-2 hardcoded everything for the meteorite set: the rename map and numeric
columns in ``load.py``, the plausibility bounds in ``checks/units.py``, the unique
key in ``checks/duplicates.py``. Adding a second dataset meant editing all three.

A ``DatasetSpec`` collects that knowledge as *data*. The loader and the checks read
it instead of carrying their own constants, so onboarding a new dataset is: add one
spec here, author its rules, done — no check code changes. The check *engines* stay
generic; only the rules differ per dataset.

``meteorites`` reproduces the original hardcoded behaviour exactly and stays as the
proving ground (it is the fixture that exercises the range / null-island checks).
``lemat_bulk`` is the flagship **and** the default — a tabular sample of
LeMaterial/LeMat-Bulk (DFT materials properties).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# src/auditor/datasets.py -> parents[2] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ConsistencyRule:
    """One group-consistency expectation: *rows sharing a key should agree.*

    The engine in ``checks/consistency.py`` groups rows by ``group_by`` and, within
    each group, checks that ``columns`` agree. Two modes:

    * ``"exact"`` — the values must be *identical* (categorical / structural
      invariants, e.g. the same material id must always carry the same atom count
      and formula). Any variation is a finding.
    * ``"numeric"`` — a numeric column must agree within ``tolerance`` across the
      group, optionally after dividing by ``normalize_by`` (e.g. per-atom). Use for
      quantities that *should* be close but may drift.

    A physics note that shaped this design: DFT total energies are **not** comparable
    across exchange-correlation functionals (PBE vs PBEsol vs SCAN have different
    references), so a numeric rule on ``energy`` grouped across functionals would
    flag expected behaviour, not errors. That is why LeMat-Bulk uses an ``exact``
    rule on *structure* (which must be invariant) and does not compare energies.
    """

    group_by: str
    """Column whose equal values define a group (typically a supposed unique id)."""

    columns: tuple[str, ...]
    """Columns expected to agree within each group."""

    mode: str = "exact"
    """``"exact"`` (identical values) or ``"numeric"`` (agree within tolerance)."""

    tolerance: float = 0.0
    """Numeric mode: max allowed spread (max - min) within a group."""

    relative: bool = False
    """Numeric mode: if true, ``tolerance`` is a fraction of the group's median
    magnitude rather than an absolute amount."""

    normalize_by: str | None = None
    """Numeric mode: divide each value by this column before comparing (e.g.
    ``"nsites"`` to compare energy per atom rather than extensive total)."""


@dataclass(frozen=True)
class NearDupRule:
    """A near-duplicate expectation: *distinct entities should not share content.*

    The engine in ``checks/near_dup.py`` groups rows by ``content_key`` — a column
    whose equal value means "same underlying thing" (a structural hash, a
    normalized text, a fingerprint). When one ``content_key`` is shared by rows
    carrying *different* ``identity`` values, those rows are probably duplicate
    records of a single entity, recorded under separate ids.

    On LeMat-Bulk, ``entalpic_fingerprint`` hashes the structure and ``immutable_id``
    is the provenance id. One fingerprint spanning several ids means the same
    material was ingested twice from different source databases — exactly the
    harmonization mess the flagship was chosen to exercise. This is the *exact*
    (hash-collision) tier; fuzzy embedding similarity is the deferred extension.

    With ``identity=None`` the rule flags any ``content_key`` shared by more than one
    row, regardless of id.
    """

    content_key: str
    """Column whose equal value marks two rows as the same content."""

    identity: str | None = None
    """Column expected to be unique per real entity. A ``content_key`` group that
    spans more than one distinct ``identity`` is flagged. ``None`` flags any shared
    ``content_key``."""


@dataclass(frozen=True)
class LabelRule:
    """A categorical-plausibility expectation: a value should make sense given the row.

    The engine in ``checks/labels.py`` asks the LOCAL LLM, per sampled row, whether the
    value in ``column`` is plausible given the other fields named in ``context_columns``
    and the dataset's ``domain_context``. Unlike the deterministic checks this is
    *judgement*, not arithmetic, so confident negatives are ``warn`` (a human confirms)
    and the check SAMPLES rather than scans — LLM calls are expensive. Empty
    ``label_rules`` disables the check entirely.

    Honesty note: both science flagships have near-zero noisy categoricals (LeMat
    ``functional`` is a recorded fact, not a judgement call; meteorite ``recclass``-vs-
    ``mass`` is only borderline), so this is primarily a fixture demonstration — the
    field exists for datasets whose categoricals are human-entered and error-prone.
    """

    column: str
    """The categorical column whose value is judged."""

    context_columns: tuple[str, ...] = ()
    """Other columns shown to the model as evidence for the judgement."""

    allowed: tuple[str, ...] = ()
    """Optional closed vocabulary. A value outside it is flagged deterministically
    (no LLM call); empty means an open set (every value is judged by the model)."""

    max_calls: int = 25
    """Per-rule sampling cap on distinct cases judged (backstop, not a target)."""


@dataclass(frozen=True)
class FormulaRule:
    """A chemical-formula agreement expectation (the opt-in materials domain pack).

    The engine in ``checks/formula.py`` parses the named formula columns and verifies
    they encode one composition. ``reduced`` (or ``descriptive`` if reduced is absent)
    is the canonical anchor; every other named column is checked against it:

    * ``descriptive`` and ``reduced`` must reduce to the same element->count map.
    * ``anonymous`` (which drops element identity) must match the anchor's *count*
      multiset, e.g. reduced ``Cd2InP`` -> counts ``[2,1,1]`` -> anonymous ``A2BC``.
    * ``elements`` (a list like ``"Cd-In-P"``) must equal the parsed element set.
    * ``nelements`` must equal the number of distinct elements.

    Only the columns actually named (and present in the data) are compared, so a
    dataset that carries a subset still works. Empty ``formula_rules`` disables the
    check entirely — it is dormant for every non-materials dataset.
    """

    reduced: str | None = None
    """Reduced formula column (alphabetical, GCD-reduced). The preferred anchor."""

    descriptive: str | None = None
    """Descriptive formula column (explicit per-element counts). Anchor fallback."""

    anonymous: str | None = None
    """Anonymized formula column (``A2B3`` style); compared by count multiset only."""

    elements: str | None = None
    """Optional element-list column (e.g. ``"Cd-In-P"``) cross-checked against the set."""

    nelements: str | None = None
    """Optional distinct-element-count column cross-checked against the composition."""


@dataclass(frozen=True)
class DatasetSpec:
    """Everything the loader and checks need to know about one dataset."""

    name: str
    """Short id used on the CLI (``--dataset <name>``) and in messages."""

    filename: str
    """CSV file under ``data/``. Loaded by default when no source is given."""

    source_url: str = ""
    """Provenance, kept in code rather than just shell history."""

    rename_map: dict[str, str] = field(default_factory=dict)
    """Column renames applied after lower-casing, e.g. ``{"mass": "mass_g"}`` to
    encode the unit in the name. Every other column is simply lower-cased."""

    numeric_columns: tuple[str, ...] = ()
    """Columns coerced to numeric on load (``errors="coerce"``): the *type* is
    fixed, the *values* are never touched."""

    key_column: str | None = None
    """Column expected to be a unique identifier (drives the duplicate-key check).
    ``None`` disables that check."""

    range_rules: dict[str, dict] = field(default_factory=dict)
    """Plausibility bounds per column for the units check. Same schema the engine
    in ``checks/units.py`` already consumes: ``{"min": .., "max": ..,
    "exclusive_min": bool, "exclusive_max": bool}``."""

    null_island: bool = False
    """Whether to run the ``(reclat, reclong) == (0, 0)`` placeholder check
    (meteorite-specific; off for datasets without coordinates)."""

    consistency_rules: tuple[ConsistencyRule, ...] = ()
    """Group-consistency expectations for ``checks/consistency.py``. Empty disables
    the check. See :class:`ConsistencyRule`."""

    near_dup_rules: tuple[NearDupRule, ...] = ()
    """Near-duplicate expectations for ``checks/near_dup.py``. Empty disables the
    check. See :class:`NearDupRule`."""

    pii_text_columns: tuple[str, ...] = ()
    """Free-text columns to scan for personal data in ``checks/pii.py``. Empty
    disables the check. Both science flagships have none (so PII is demonstrated on
    a fixture); the field exists for datasets that carry user-authored text."""

    label_rules: tuple[LabelRule, ...] = ()
    """Categorical-plausibility expectations for ``checks/labels.py`` (LLM-judged).
    Empty disables the check. See :class:`LabelRule`. Both flagships leave this empty
    (their categoricals are facts, not error-prone labels), so it is demonstrated on a
    fixture; the field exists for datasets with human-entered categoricals."""

    formula_rules: tuple[FormulaRule, ...] = ()
    """Chemical-formula agreement expectations for ``checks/formula.py`` (the opt-in
    materials domain pack). Empty disables the check, so it is dormant for every
    non-materials dataset. See :class:`FormulaRule`."""

    categorical_columns: tuple[str, ...] = ()
    """Hint for ``load.profile``: columns to show value-counts for."""

    domain_context: str = ""
    """Concrete domain grounding for the Phase-3 LLM checks — what the columns
    mean, their units, and what "normal" looks like. This is *context, not a
    persona*: it gives the model information to reason with, not an identity to
    role-play (which studies show rarely helps and can hurt calibration). Injected
    into judge prompts by ``llm.py``; could later be generated by the research
    phase. Keep it factual and specific (units, ranges, expected invariants)."""

    @property
    def path(self) -> Path:
        return REPO_ROOT / "data" / self.filename


METEORITES = DatasetSpec(
    name="meteorites",
    filename="meteorites.csv",
    source_url=(
        "https://raw.githubusercontent.com/pylablanche/Kaggle_Meteorites/"
        "master/meteorite-landings.csv"
    ),
    rename_map={"mass": "mass_g"},
    numeric_columns=("mass_g", "year", "reclat", "reclong"),
    key_column="id",
    range_rules={
        "reclat": {"min": -90, "max": 90},
        "reclong": {"min": -180, "max": 180},  # catches the 354.47 outlier
        "year": {"max": 2025},                  # no meteorite from the future
        "mass_g": {"min": 0, "exclusive_min": True},  # mass must be strictly > 0
    },
    null_island=True,
    categorical_columns=("nametype", "fall"),
    domain_context=(
        "NASA Meteorite Landings: one row per recovered meteorite. "
        "mass_g is mass in grams (strictly positive). year is the year the "
        "meteorite fell or was found (cannot be in the future). reclat/reclong "
        "are recovery latitude/longitude in decimal degrees ([-90,90] / "
        "[-180,180]); coordinates of exactly (0, 0) are a missing-location "
        "placeholder, not a real site in the Gulf of Guinea. recclass is the "
        "meteorite classification (e.g. L5, H6, EH4). fall is one of "
        "{Fell, Found}; nametype one of {Valid, Relict}."
    ),
)

LEMAT_BULK = DatasetSpec(
    name="lemat_bulk",
    filename="lemat_bulk_sample.csv",
    source_url="https://huggingface.co/datasets/LeMaterial/LeMat-Bulk",
    rename_map={},
    numeric_columns=(
        "nelements", "nsites", "nperiodic_dimensions",
        "energy", "total_magnetization", "dos_ef",
    ),
    # immutable_id should identify one material; in the harmonized multi-functional
    # data the same id recurs (pbe/pbesol/scan), which is exactly what we surface.
    key_column="immutable_id",
    range_rules={
        # Bulk crystals are 3D-periodic; anything else is a structural anomaly.
        "nperiodic_dimensions": {"min": 3, "max": 3},
        "nelements": {"min": 1},  # a material has at least one element
        "nsites": {"min": 1},     # ...and at least one atomic site
    },
    null_island=False,
    # The same immutable_id recurs across DFT functionals (expected). Whatever else
    # differs between those rows, they describe the SAME material, so the structural
    # descriptors must be identical. Energies are deliberately excluded: they vary
    # legitimately across functionals (see ConsistencyRule's physics note), so
    # comparing them would manufacture false positives. This rule is honestly clean
    # on the current sample; it exists to catch a harmonization defect (two distinct
    # structures linked under one id) the moment one appears.
    consistency_rules=(
        ConsistencyRule(
            group_by="immutable_id",
            columns=(
                "nsites", "nelements", "nperiodic_dimensions",
                "chemical_formula_reduced", "chemical_formula_descriptive",
                "chemical_formula_anonymous", "elements",
            ),
            mode="exact",
        ),
    ),
    # entalpic_fingerprint hashes the structure; immutable_id is the provenance id.
    # One fingerprint under several ids = the same material ingested twice from
    # different source DBs. Unlike the consistency rule, this one fires on the real
    # sample (119 fingerprint groups span >1 id), the genuine harmonization signal.
    near_dup_rules=(
        NearDupRule(content_key="entalpic_fingerprint", identity="immutable_id"),
    ),
    # The opt-in materials domain pack: the three OPTIMADE formula columns (plus the
    # elements list and nelements count) are redundant encodings of one composition,
    # so they must agree. Honestly clean on the sample; it catches an ingest defect
    # (mismatched formula representations) the moment one appears.
    formula_rules=(
        FormulaRule(
            reduced="chemical_formula_reduced",
            descriptive="chemical_formula_descriptive",
            anonymous="chemical_formula_anonymous",
            elements="elements",
            nelements="nelements",
        ),
    ),
    categorical_columns=("functional", "cross_compatibility"),
    domain_context=(
        "LeMaterial/LeMat-Bulk: DFT-computed properties of bulk inorganic "
        "crystals, harmonized from Materials Project, OQMD and Alexandria. "
        "energy is the total DFT energy in eV (extensive, so it scales with "
        "nsites; compare per-atom, not absolute). dos_ef is the density of "
        "states at the Fermi level (states/eV). total_magnetization is the net "
        "magnetic moment in Bohr magnetons. nelements and nsites are counts (>= 1); "
        "nperiodic_dimensions is 3 for bulk crystals. functional is the DFT "
        "exchange-correlation functional, one of {pbe, pbesol, scan}. The three "
        "formula columns (descriptive, reduced, anonymous) describe the same "
        "composition and should be mutually consistent. The same immutable_id can "
        "recur across functionals (expected), but the computed properties for one "
        "material should be physically consistent."
    ),
)

DATASETS: dict[str, DatasetSpec] = {d.name: d for d in (METEORITES, LEMAT_BULK)}
# The flagship is the default; meteorites stays as the documented proving ground
# (and the fixture that exercises the range / null-island checks LeMat-Bulk doesn't).
DEFAULT = LEMAT_BULK


def get(name: str | None = None) -> DatasetSpec:
    """Look up a spec by name. ``None`` returns the default (LeMat-Bulk)."""
    if name is None:
        return DEFAULT
    try:
        return DATASETS[name]
    except KeyError:
        raise SystemExit(
            f"unknown dataset {name!r}; choose from {sorted(DATASETS)}"
        ) from None
