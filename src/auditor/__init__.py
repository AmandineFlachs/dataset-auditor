"""dataset-auditor: point heuristics + a local LLM at a scientific dataset and
flag PII, unit/format inconsistencies, label noise, and duplicates."""

from auditor.models import Finding, Severity

__all__ = ["Finding", "Severity"]
__version__ = "0.1.0"
