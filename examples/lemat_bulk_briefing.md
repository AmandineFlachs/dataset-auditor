# Research briefing: lemat_bulk

This dataset contains DFT-computed properties of bulk inorganic crystals, including energy, magnetization, and density of states at the Fermi level. It also includes metadata about the crystal structure and computational method used.

## Columns

### `immutable_id`
- **Likely meaning:** Unique identifier for each material entry
- **Plausible range:** Arbitrary string values, unique for each row
- **Pitfalls:** None expected, as it should uniquely identify each record

### `chemical_formula_descriptive`
- **Likely meaning:** Descriptive chemical formula of the material
- **Plausible range:** String representations of chemical formulas, should match the other formula columns
- **Pitfalls:** Should be consistent with chemical_formula_reduced and chemical_formula_anonymous

### `chemical_formula_reduced`
- **Likely meaning:** Reduced chemical formula of the material
- **Plausible range:** String representations of chemical formulas, should match the other formula columns
- **Pitfalls:** Should be consistent with chemical_formula_descriptive and chemical_formula_anonymous

### `chemical_formula_anonymous`
- **Likely meaning:** Anonymous chemical formula of the material
- **Plausible range:** String representations of chemical formulas, should match the other formula columns
- **Pitfalls:** Should be consistent with chemical_formula_descriptive and chemical_formula_reduced

### `elements`
- **Likely meaning:** List of elements present in the material
- **Plausible range:** Comma-separated list of element symbols
- **Pitfalls:** Should be consistent with nelements and the chemical formula columns

### `nelements`
- **Likely meaning:** Number of distinct elements in the material
- **Units:** count
- **Plausible range:** Integer between 1 and 7
- **Pitfalls:** Should be consistent with the elements list and chemical formula columns

### `nsites`
- **Likely meaning:** Number of sites in the crystal structure
- **Units:** count
- **Plausible range:** Integer between 1 and 200
- **Pitfalls:** Should be consistent with the crystal structure and number of atoms

### `nperiodic_dimensions`
- **Likely meaning:** Number of periodic dimensions in the crystal structure
- **Units:** count
- **Plausible range:** Integer, always 3 for bulk crystals
- **Pitfalls:** Should always be 3 for bulk crystals

### `energy`
- **Likely meaning:** Total DFT energy of the material
- **Units:** eV
- **Plausible range:** Float between -2496 and 1804
- **Pitfalls:** Should be consistent with nsites and physical properties

### `total_magnetization`
- **Likely meaning:** Net magnetic moment of the material
- **Units:** Bohr magnetons
- **Plausible range:** Float between -32.61 and 356.7
- **Pitfalls:** May have missing values due to non-magnetic materials or incomplete calculations

### `dos_ef`
- **Likely meaning:** Density of states at the Fermi level
- **Units:** states/eV
- **Plausible range:** Float between -6.072 and 130.2
- **Pitfalls:** High percentage of missing values may indicate incomplete calculations or non-metallic materials

### `functional`
- **Likely meaning:** DFT exchange-correlation functional used
- **Plausible range:** String values 'pbe', 'pbesol', or 'scan'
- **Pitfalls:** Should be consistent with the computational method used

### `cross_compatibility`
- **Likely meaning:** Boolean indicating if the material is cross-compatible
- **Units:** boolean
- **Plausible range:** 0 or 1
- **Pitfalls:** Binary value, no further unit or range issues

### `entalpic_fingerprint`
- **Likely meaning:** Entropic fingerprint of the material
- **Plausible range:** String representation of the fingerprint
- **Pitfalls:** Should be consistent with the material's thermodynamic properties

### `last_modified`
- **Likely meaning:** Timestamp of the last modification date
- **Units:** date/time
- **Plausible range:** Date and time strings
- **Pitfalls:** Should be a valid date/time format

## Dataset-level pitfalls

- Inconsistent chemical formula representations across descriptive, reduced, and anonymous columns
- Missing values in total_magnetization and dos_ef may indicate incomplete or inconsistent data
- Potential inconsistencies in energy scaling with nsites
- Cross-compatibility boolean may require additional context for interpretation

## Suggested checks (advisory — author by hand, not auto-applied)

- Check that immutable_id is unique for each material entry
- Verify consistency between chemical_formula_descriptive, chemical_formula_reduced, and chemical_formula_anonymous
- Ensure nelements matches the count of distinct elements in the elements list
- Validate that nperiodic_dimensions is always 3 for bulk crystals
- Confirm that energy values are consistent with nsites and physical properties
- Identify patterns or anomalies in missing total_magnetization and dos_ef values
- Cross-check functional consistency with computational methods
- Validate cross_compatibility boolean against known standards or criteria
- Ensure entalpic_fingerprint is consistent with the material's thermodynamic properties
- Verify that last_modified timestamps are in a valid date/time format

---
*Generated locally from dataset metadata only (no raw rows). Advisory, not auto-applied.*