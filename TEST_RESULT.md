# Verification: v2.3.5-P0-ID

- Baseline regression: 175 passed, 1 skipped.
- Updated test suite: 203 passed, 1 skipped.
- New identification/selector regression cases: 28.
- verify_id.ipynb: 10 code cells executed, including 5 separate assert cells.
- Python compileall: passed.
- Identifier normalization tested for alternate field names, copied whitespace/zero-width characters, and conflicting identifiers.
- Mock UI checks: unknown-list column order, readable selection labels, exact control-number links, filtering, and old-session migration.
- Sorting/classification test with 263 SYNTHETIC records: passed. These are not the user's actual API records.
- No personal API keys were supplied or used. No research-note/AI prompt/report-generation modules were rewritten.

## Not verified

- Live National Assembly Library API search with the user's credentials.
- Classification of the user's actual 263 records.
- Real Streamlit browser rendering or the user's local/Cloud deployment.
- The existing Streamlit AppTest was skipped because Streamlit is not installed. Installing it was attempted but package download failed due to unavailable network/DNS.

The current screenshot's manual-classification form matches text in archived 2.3.2/2.3.3 sources; it is absent from the retained 2.3.4-P0 archive. This does not establish which local file/Cloud branch the user is executing. The new direct entrypoint, visible build ID, and check_install.py are provided to verify that.
