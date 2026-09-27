#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Retired unsafe forecast-log backfill entry point.

The former implementation fitted one model with later observations and then
used it to manufacture predictions for earlier dates. Those rows were not
point-in-time forecasts and must not be used for accuracy or shock analysis.

Valid evaluation rows are now appended by ``analyze_us_market_state.py`` on
each market date and are never recomputed retroactively. A historical rebuild
would require a dedicated purged walk-forward implementation; failing loudly
here prevents accidental reintroduction of look-ahead bias.
"""


def main() -> int:
    print(
        "ERROR: backfill_forecast_log.py is retired because the old backfill "
        "introduced look-ahead bias. Run run_all.py on each market date to "
        "build the point-in-time evaluation log."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
