# Triage: lemat_bulk

The audit identified duplicate entries based on 'immutable_id', near duplicates based on 'entalpic_fingerprint', and a high null rate for 'dos_ef'.

## Issues, highest priority first

### [HIGH] duplicates.duplicate_key - immutable_id (122 rows)
- Duplicate 'immutable_id' value; this column is expected to be unique.
- **Suggested fix:** Investigate why the identifier repeats; keys must be unique.
- **What to check:** Verify if the duplicate 'immutable_id' values represent different materials or are mistakenly duplicated.

### [MEDIUM] near_dup.shared_content - entalpic_fingerprint (240 rows)
- Distinct records share identical content; likely the same entity recorded more than once.
- **Suggested fix:** Confirm whether these are intentional cross-source records or duplicates to merge.
- **What to check:** Check if the near-duplicate records with identical 'entalpic_fingerprint' actually represent the same material recorded multiple times.

### [MEDIUM] schema.high_null_rate - dos_ef (1 rows)
- Column 'dos_ef' is 36.8% null (over the 10% threshold).
- **Suggested fix:** Decide whether to impute, drop the column, or document the gap.
- **What to check:** Investigate why 'dos_ef' has a high null rate and determine if these nulls are due to missing data or if they are expected to be null.

---
*Priority is deterministic (severity, then affected rows). The summary and 'what to check' lines are an advisory orientation from a local model -- it suggests what to verify, it does not decide what is a real defect.*