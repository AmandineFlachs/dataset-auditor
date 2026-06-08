# Research briefing: meteorites

This dataset contains information about meteorites that have been recovered. Each row represents a single meteorite, with details such as its classification, mass, and location of recovery.

## Columns

### `name`
- **Likely meaning:** Name of the meteorite
- **Plausible range:** Alphanumeric string representing the name of the meteorite
- **Pitfalls:** Potential issues include non-standard naming conventions or duplicate names.

### `id`
- **Likely meaning:** Unique identifier for the meteorite
- **Plausible range:** Integer ranging from 1 to 57460
- **Pitfalls:** Possible issues include gaps in the sequence or duplicate IDs.

### `nametype`
- **Likely meaning:** Type of name given to the meteorite
- **Plausible range:** Values are 'Valid' or 'Relict'
- **Pitfalls:** Issues may arise if the values are inconsistent or incorrectly labeled.

### `recclass`
- **Likely meaning:** Classification of the meteorite
- **Plausible range:** String representing the classification code (e.g., L5, H6, EH4)
- **Pitfalls:** Potential issues include incorrect classifications or inconsistent formatting.

### `mass_g`
- **Likely meaning:** Mass of the meteorite in grams
- **Units:** grams
- **Plausible range:** Float ranging from 0 to 600,000,000 grams
- **Pitfalls:** Issues may include negative values or unrealistic high masses.

### `fall`
- **Likely meaning:** Whether the meteorite fell or was found
- **Plausible range:** Values are 'Found' or 'Fell'
- **Pitfalls:** Potential issues include inconsistent labeling or incorrect categorization.

### `year`
- **Likely meaning:** Year the meteorite was found or fell
- **Units:** years
- **Plausible range:** Float ranging from 301 to 2501 years
- **Pitfalls:** Issues may include future dates or unrealistic historical dates.

### `reclat`
- **Likely meaning:** Latitude of the recovery site
- **Units:** decimal degrees
- **Plausible range:** Float ranging from -90 to 90 degrees
- **Pitfalls:** Potential issues include out-of-range values or missing data.

### `reclong`
- **Likely meaning:** Longitude of the recovery site
- **Units:** decimal degrees
- **Plausible range:** Float ranging from -180 to 180 degrees
- **Pitfalls:** Issues may include out-of-range values or missing data.

### `geolocation`
- **Likely meaning:** Geographic location of the recovery site
- **Units:** latitude and longitude
- **Plausible range:** String representation of latitude and longitude
- **Pitfalls:** Potential issues include missing data or invalid coordinate pairs.

## Dataset-level pitfalls

- Missing or inconsistent data in the geolocation field.
- Incorrect or inconsistent classification codes in the recclass field.
- Unrealistic or impossible values in the mass_g field.
- Future dates or unrealistic historical dates in the year field.

## Suggested checks (advisory — author by hand, not auto-applied)

- Check for missing or inconsistent data in the geolocation field.
- Verify the consistency and correctness of classification codes in the recclass field.
- Validate the plausibility of mass values in the mass_g field.
- Ensure the year field does not contain future dates or unrealistic historical dates.

---
*Generated locally from dataset metadata only (no raw rows). Advisory, not auto-applied.*