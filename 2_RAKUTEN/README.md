# Finance Dashboard

## Overview

This folder is intentionally runnable as-is.

```bash
python rakuten_update.py
```

The update script fetches online fund data, appends normalized market records,
syncs any missing historical NAV dates from the fund chart data, and regenerates
`dashboard.html`.

Historical NAV can be restored from the embedded chart data on each fund detail
page:

```bash
python rakuten_update.py --backfill all --skip-latest
```

Normal updates already run the same missing-date sync before fetching the latest
online data. Use `--build-only` only when you want to rebuild `dashboard.html`
from the existing local `daily_records.json` without network access.

The automatic all-product history sync is best-effort: if one Rakuten chart is
temporarily unavailable, the run prints a warning and still updates the latest
prices. An explicit `--backfill <short name>` remains strict and exits with an
error so a requested product cannot be silently skipped.

## Operational Files

- `fund_master.json`: Product and broker master. Add or disable products here.
- `holdings_input.csv`: Local holding input. Edit this for normal operation.
- `holdings.json`: Legacy/private holding JSON fallback.
- `daily_records.json`: Normalized market time series cache.
- `dashboard.html`: Viewer output.
- `rakuten_update.py`: Single Python entry point for fetch, backfill, shaping, and HTML generation.

## Add A Product

1. Add a row object to `fund_master.json` under `products`.
2. Set `enabled` to `true`.
3. Add matching `short` rows to `holdings_input.csv` by account.
4. Run `python rakuten_update.py`.

If the trade is not executed yet and units are unknown, leave `units` empty,
set `status=planned`, and enter the order amount in `planned_value`.
For Excel compatibility, keep `holdings_input.csv` as UTF-8 with BOM.
After the trade-date NAV is available in `daily_records.json`, the script
automatically calculates `units` from `planned_value`, changes the row to
`status=active`, and keeps the row as a separate purchase lot. This preserves
trade timing and per-lot gains in the portfolio view.

To initialize past values for the new product, run:

```bash
python rakuten_update.py --backfill <short name> --skip-latest
```

`rakuten_update.py` is the stable execution entry point.

## Publish Local Holdings To GitHub

This folder is not auto-pushed from the local machine. After local purchase-lot
maintenance, publish the selected Rakuten files explicitly:

```bash
python publish_rakuten_to_github.py
GITHUB_TOKEN=... python publish_rakuten_to_github.py --push
```

The default publish set is:

- `holdings_input.csv`
- `fund_master.json`
- `rakuten_update.py`
- `README.md`
- `publish_rakuten_to_github.py`

`daily_records.json` and `dashboard.html` are normally left to GitHub Actions,
because the scheduled workflow refreshes market prices and regenerates the
viewer. To overwrite generated files manually, pass `--include-generated`.

## Holdings Privacy

`holdings_input.csv` is used for local runs. For public repositories, you can keep
holdings out of GitHub by setting the GitHub Actions secret
`RAKUTEN_HOLDINGS_JSON` to the same JSON content. When the secret is present,
it is used before the local file.
