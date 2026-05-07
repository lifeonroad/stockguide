# Changelog

## [2026-05-07] — Data Source Toggle + Cache Fixes

### Changed
- **`backend/data_client.py`**: Added `DEFEATBETA_ENABLED` environment variable toggle (default: `1`). When set to `0`, all data functions bypass defeatbeta and use yfinance/yahooquery directly. Each function checks the flag at entry — no duplicate code paths.
- **`backend/main.py`**: Added `Cache-Control: no-cache` headers to `index.html` response to prevent stale browser caching.
- **`frontend/index.html`**: Bumped script cache-busting versions to `?v=17`.

### Fixed
- **`frontend/index.html`**: ID mismatch — `superinvestor-view` → `superinvestors-view` (matches `app.js` tab logic).
- **`frontend/index.html`**: ID mismatch — `moonshot-view` → `moonshots-view` (matches `app.js` tab logic).
- **`frontend/index.html`**: Removed duplicate `moonshot-view` div that appeared twice in the file.
- **`frontend/index.html`**: Removed orphaned `</main>` closing tag with no matching open tag.

### New Config
| Variable | Default | Description |
|---|---|---|
| `DEFEATBETA_ENABLED` | `1` | Set to `0` to disable defeatbeta and fall back to yfinance/yahooquery |

### Usage
```bash
# Defeatbeta enabled (default)
python3 run.py

# yfinance-only mode
DEFEATBETA_ENABLED=0 python3 run.py
```
