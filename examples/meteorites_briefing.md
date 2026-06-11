# Research briefing: meteorites

The dataset contains information on recovered meteorites, with 45,716 rows. The data includes details such as name, ID, classification, mass, year of fall, and geographic coordinates. Some columns have missing values, particularly reclat, reclong, and geolocation. The year is a float, which may be an issue as it should be an integer. The mass is in grams, and the coordinates are in decimal degrees.

## Columns

### `name`
- **Likely meaning:** Name of the meteorite
- **Plausible range:** Text string (no specific length constraint)
- **Pitfalls:** Missing values are 0%, so no issues here. However, ensure that names are unique and correctly spelled.

### `id`
- **Likely meaning:** Unique identifier for the meteorite
- **Plausible range:** Positive integer (no specific range constraint)
- **Pitfalls:** Values range from 1 to 57,460. Ensure that IDs are unique and correctly assigned.

### `nametype`
- **Likely meaning:** Type of name validity
- **Plausible range:** Either 'Valid' or 'Relict'
- **Pitfalls:** Only two possible values. Ensure that entries are correctly categorized as 'Valid' or 'Relict'.

### `recclass`
- **Likely meaning:** Classification of the meteorite
- **Plausible range:** Text string (e.g., 'L5', 'H6', 'EH4')
- **Pitfalls:** Ensure that classifications follow the standard format and are correctly spelled.

### `mass_g`
- **Likely meaning:** Mass of the meteorite in grams
- **Units:** grams
- **Plausible range:** Strictly positive float (e.g., 1.328e+04 grams)
- **Pitfalls:** Values can be zero, which is invalid. Ensure that mass is strictly positive.

### `fall`
- **Likely meaning:** Whether the meteorite fell or was found
- **Plausible range:** Either 'Fell' or 'Found'
- **Pitfalls:** Ensure that entries are correctly categorized as 'Fell' or 'Found'.

### `year`
- **Likely meaning:** Year the meteorite fell or was found
- **Plausible range:** Integer between 301 and 2501
- **Pitfalls:** The data type is float, which may be an issue. Ensure that the year is an integer and not in the future.

### `reclat`
- **Likely meaning:** Latitude of the recovery location
- **Units:** decimal degrees
- **Plausible range:** Between -90 and 90
- **Pitfalls:** 16% missing. Ensure that values are within the valid range for latitude and that missing values are properly handled.

### `reclong`
- **Likely meaning:** Longitude of the recovery location
- **Units:** decimal degrees
- **Plausible range:** Between -180 and 180
- **Pitfalls:** 16% missing. Ensure that values are within the valid range for longitude and that missing values are properly handled.

### `geolocation`
- **Likely meaning:** Geolocation information (possibly a string representation of coordinates)
- **Plausible range:** Text string (no specific length constraint)
- **Pitfalls:** 16% missing. Ensure that geolocation data is consistent with reclat and reclong, and that missing values are properly handled.

## Dataset-level pitfalls

- The year is stored as a float, which may be an issue as it should be an integer.
- reclat and reclong have 16% missing values. Ensure that missing values are properly handled and that the data is consistent with the coordinates.
- geolocation has 16% missing values. Ensure that geolocation data is consistent with reclat and reclong, and that missing values are properly handled.

## Suggested checks (advisory — author by hand, not auto-applied)

- Check that the 'year' column contains only integer values (no decimal points).
- Verify that 'reclat' and 'reclong' values are within the valid ranges of -90 to 90 and -180 to 180, respectively.
- Ensure that 'geolocation' data is consistent with 'reclat' and 'reclong' when both are present.
- Confirm that 'mass_g' is strictly positive (no zero or negative values).
- Check that 'nametype' and 'fall' columns only contain the values 'Valid'/'Relict' and 'Fell'/'Found', respectively.

---
*Generated locally from dataset metadata only (no raw rows). Advisory, not auto-applied.*