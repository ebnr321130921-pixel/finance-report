# Finance Dashboard

## Overview

This folder is intentionally runnable as-is.

```bash
python rakuten_update.py
```

The update script fetches online fund data, appends normalized market records,
and regenerates `dashboard.html`.

Historical NAV can be restored from the embedded chart data on each fund detail
page:

```bash
python rakuten_update.py --backfill all --skip-latest
```

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

## Holdings Privacy

`holdings_input.csv` is used for local runs. For public repositories, you can keep
holdings out of GitHub by setting the GitHub Actions secret
`RAKUTEN_HOLDINGS_JSON` to the same JSON content. When the secret is present,
it is used before the local file.
