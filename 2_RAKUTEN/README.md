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
- `holdings.json`: Private holding units by account and portfolio start/change metadata.
- `daily_records.json`: Normalized market time series cache.
- `dashboard.html`: Viewer output.
- `rakuten_update.py`: Single Python entry point for fetch, backfill, shaping, and HTML generation.

## Add A Product

1. Add a row object to `fund_master.json` under `products`.
2. Set `enabled` to `true`.
3. Add matching `short` rows to `holdings.json` by account. Use `units=0` until held.
4. Run `python rakuten_update.py`.

To initialize past values for the new product, run:

```bash
python rakuten_update.py --backfill <short name> --skip-latest
```

`rakuten_update.py` is the stable execution entry point.

## Holdings Privacy

`holdings.json` is used for local runs. For public repositories, you can keep
holdings out of GitHub by setting the GitHub Actions secret
`RAKUTEN_HOLDINGS_JSON` to the same JSON content. When the secret is present,
it is used before the local file.
