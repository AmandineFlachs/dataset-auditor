# Triage: lemat_bulk

The audit identified potential data-quality issues in the lemat_bulk dataset, including duplicate immutable_id entries and shared entalpic_fingerprint values, as well as a high null rate in the dos_ef column.

## Issues, highest priority first

### [HIGH] duplicates.duplicate_key - immutable_id (122 rows)
- Duplicate 'immutable_id' value; this column is expected to be unique.
- **Suggested fix:** Investigate why the identifier repeats; keys must be unique.
- **What to check:** Check if the duplicate immutable_id values are due to intentional re-recordings of the same material across different functionals, as the domain context allows the same immutable_id to recur across functionals.

### [MEDIUM] near_dup.shared_content - entalpic_fingerprint (240 rows)
- Distinct records share identical content; likely the same entity recorded more than once.
- **Suggested fix:** Confirm whether these are intentional cross-source records or duplicates to merge.
- **What to check:** Verify if the shared entalpic_fingerprint values indicate duplicate materials or if they result from different but chemically similar compounds with identical fingerprints.

### [MEDIUM] schema.high_null_rate - dos_ef (1 rows)
- Column 'dos_ef' is 36.8% null (over the 10% threshold).
- **Suggested fix:** Decide whether to impute, drop the column, or document the gap.
- **What to check:** Assess whether the 36.8% null rate in dos_ef is due to missing data or if it reflects a known issue in the dataset's collection or harmonization process.

---
*Priority is deterministic (severity, then affected rows). The summary and 'what to check' lines are an advisory orientation from a local model -- it suggests what to verify, it does not decide what is a real defect.*