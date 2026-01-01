#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent

PIPELINE = [
    ("Fetch Market Factors", "fetch_us_market_factors.py"),
    ("Analyze Market State", "analyze_us_market_state.py"),
    # Regression は Analyze 内から呼び出す（Run_all では実行しない）
    ("Aegis Sigma Diagnostics", "aegis_sigma_external_shock.py"),
    ("Build Market Summary", "build_market_summary.py"),
    ("Build HTML Viewer", "build_us_index_viewer.py"),
]


def run_step(title, script):
    script_path = BASE / script
    if not script_path.exists():
        print(f"❌ Script not found: {script}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"▶ {title}")
    print(f"▶ Script: {script}")
    print(f"▶ Start : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=BASE
    )

    if result.returncode != 0:
        print("\n❌ ERROR occurred. Pipeline stopped.")
        sys.exit(result.returncode)

    print(f"✅ Finished: {title}")

def main():
    print("\n🚀 US Index Full Pipeline START")
    print(f"Base Directory: {BASE}")

    for title, script in PIPELINE:
        run_step(title, script)

    print("\n🎉 ALL PIPELINE COMPLETED SUCCESSFULLY")
    print(f"Finish Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

if __name__ == "__main__":
    main()
