#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Retired companion to the unsafe historical forecast backfill."""


def main() -> int:
    print(
        "ERROR: backfill_forecast_weekly.py is retired. Weekly evaluation is "
        "now built only from immutable point-in-time forecasts by "
        "Regression_Eval.py."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
