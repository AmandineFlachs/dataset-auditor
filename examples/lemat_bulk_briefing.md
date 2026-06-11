# Research briefing: lemat_bulk

The dataset contains DFT-computed properties of bulk inorganic crystals, with 25,000 entries. Key columns include material identifiers, composition descriptions, and physical properties like energy and magnetization. Missing data is present in 'total_magnetization' and 'dos_ef' columns.

## Columns

### `immutable_id`
- **Likely meaning:** Unique identifier for each material entry
- **Pitfalls:** Duplicates or inconsistent IDs across different functionals.

### `chemical_formula_descriptive`
- **Likely meaning:** Descriptive chemical formula of the material
- **Pitfalls:** Inconsistent or non-standard formula representations.

### `chemical_formula_reduced`
- **Likely meaning:** Reduced chemical formula of the material
- **Pitfalls:** Discrepancies between descriptive and reduced formulas.

### `chemical_formula_anonymous`
- **Likely meaning:** Anonymous chemical formula for privacy or anonymization
- **Pitfalls:** Inconsistent anonymization schemes across materials.

### `elements`
- **Likely meaning:** List of elements composing the material
- **Pitfalls:** Incorrect or incomplete element listings.

### `nelements`
- **Likely meaning:** Number of distinct chemical elements in the material
- **Plausible range:** 1 to 7
- **Pitfalls:** Values outside the 1-7 range or inconsistent with other composition columns.

### `nsites`
- **Likely meaning:** Total number of atomic sites in the crystal structure
- **Plausible range:** 1 to 200
- **Pitfalls:** Values outside the 1-200 range or inconsistencies with crystal structure.

### `nperiodic_dimensions`
- **Likely meaning:** Number of periodic dimensions in the crystal structure
- **Plausible range:** 3
- **Pitfalls:** Values not equal to 3, indicating possible structural errors.

### `energy`
- **Likely meaning:** Total DFT energy of the material in eV
- **Units:** eV
- **Plausible range:** -2496 to 1804
- **Pitfalls:** Unreasonably high or low values, or inconsistencies across functionals.

### `total_magnetization`
- **Likely meaning:** Net magnetic moment in Bohr magnetons
- **Units:** Bohr magnetons
- **Plausible range:** -32.61 to 356.7
- **Pitfalls:** Missing values, negative values for non-magnetic materials, or unrealistic magnitudes.

### `dos_ef`
- **Likely meaning:** Density of states at the Fermi level in states/eV
- **Units:** states/eV
- **Plausible range:** -6.072 to 130.2
- **Pitfalls:** Missing values, negative values, or values that don't align with expected physical behavior.

### `functional`
- **Likely meaning:** DFT exchange-correlation functional used for computation
- **Plausible range:** pbe, pbesol, scan
- **Pitfalls:** Invalid functional values or inconsistencies across different functionals.

### `cross_compatibility`
- **Likely meaning:** Boolean flag indicating compatibility across different functionals
- **Plausible range:** 0 or 1
- **Pitfalls:** Inconsistent values or logical contradictions with other columns.

### `entalpic_fingerprint`
- **Likely meaning:** Fingerprint or identifier for enthalpic properties
- **Pitfalls:** Inconsistent or non-standard fingerprint representations.

### `last_modified`
- **Likely meaning:** Timestamp of the last modification to the material entry
- **Units:** Date/time
- **Pitfalls:** Invalid date formats or inconsistent modification timestamps.

## Dataset-level pitfalls

- Missing values in 'total_magnetization' and 'dos_ef' columns may indicate incomplete data or errors in computation.
- Inconsistent or non-standard chemical formulas across different columns may lead to data integration issues.
- Negative values in 'total_magnetization' or 'dos_ef' could be artifacts or errors, especially for non-magnetic materials.
- Values in 'energy' that are unreasonably high or low may indicate computational errors or incorrect scaling.

## Suggested checks (advisory — author by hand, not auto-applied)

- Verify that 'nperiodic_dimensions' is consistently 3 for all entries.
- Check that 'nelements' and 'nsites' are consistent with the chemical formulas in other columns.
- Ensure that 'functional' values are only 'pbe', 'pbesol', or 'scan' and that there are no typos.
- Validate that 'cross_compatibility' is logically consistent with other properties, especially when functionals differ.
- Confirm that 'last_modified' timestamps are in a valid date format and are consistent with data entry practices.

---
*Generated locally from dataset metadata only (no raw rows). Advisory, not auto-applied.*