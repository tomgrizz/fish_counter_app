# Fish Counter Review App

A Streamlit app for reviewing Riverwatcher event logs, matching event IDs to video clips, and tallying fish counts by species and movement direction.

## Features

- Parse Riverwatcher `.log` exports to build event records.
- Index MP4 videos and match them to event IDs.
- Review events in chronological order with video playback.
- Track counts by species and movement (Up, Down, Stay).
- Export a flattened CSV of all review results.

## Requirements

- Python 3.9+ (recommended)
- Dependencies listed in `requirements.txt`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the app

```bash
streamlit run app/streamlit_app.py
```

## Data inputs

1. **Project root**: A folder containing the Riverwatcher `.log` file.
2. **Video index root**: Root folder where MP4s are stored (commonly the same as the project root).
3. **Video library root**: Optional root used to create relative paths for display and exports.

The `.log` file is expected to have a `[data]` section with lines that resemble:

```
<id> <m1> <m2> <month> <day> <hour> <minute> <+/-> <m3>
```

## Export

Use the **Export CSV** button in the Diagnostics panel to write `fish_counts_export.csv` into the project root.

## Notes

- The app stores review data in `fishcounter.sqlite` within the project root.
- Re-indexing will update event and video metadata but preserve existing review decisions.
