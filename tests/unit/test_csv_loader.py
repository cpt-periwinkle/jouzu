"""
Unit tests for backend/services/csv_loader.py.

TODO: Write these when CSV validation logic expands (e.g. when Japanese
character validation is added to the parser).

What to test:
- Valid CSV parses correctly
- Missing required columns raises ValueError
- Empty rows are skipped
- Malformed encoding raises or handles gracefully
- Non-Japanese characters in characters column pass through (known limitation)
- Extra columns are ignored
"""
