#!/bin/bash
set -o pipefail

cd -- "$(dirname -- "$0")" || exit 1

check_dependencies() {
    "$1" -c 'import numpy, pandas, pandas_market_calendars, scipy, sklearn, statsmodels, yfinance' >/dev/null 2>&1
}

us_index_python=""

if [ -x .venv/bin/python ] && check_dependencies .venv/bin/python; then
    us_index_python=.venv/bin/python
else
    for candidate in \
        "$HOME/.pyenv/versions/3.10.6/bin/python3" \
        "$HOME/.pyenv/versions/3.14.4/bin/python3" \
        /opt/homebrew/bin/python3 \
        /usr/local/bin/python3 \
        /usr/bin/python3
    do
        if [ -x "$candidate" ] && check_dependencies "$candidate"; then
            us_index_python=$candidate
            break
        fi
    done
fi

if [ -z "$us_index_python" ]; then
    bootstrap_python=""
    for candidate in \
        "$HOME/.pyenv/versions/3.10.6/bin/python3" \
        /opt/homebrew/bin/python3 \
        /usr/local/bin/python3 \
        /usr/bin/python3
    do
        if [ -x "$candidate" ]; then
            bootstrap_python=$candidate
            break
        fi
    done

    if [ -z "$bootstrap_python" ]; then
        printf 'ERROR: Python 3 が見つかりません。\n'
        exit 1
    fi

    printf '初回セットアップ: Pythonライブラリを .venv にインストールします。\n'
    "$bootstrap_python" -m venv .venv || exit 1
    .venv/bin/python -m pip install --upgrade pip || exit 1
    .venv/bin/python -m pip install -r requirements.txt || exit 1
    us_index_python=.venv/bin/python
fi

mkdir -p .logs || exit 1
us_index_log=".logs/update-$(date +%Y%m%d-%H%M%S)-$$.log"

printf '\nUS Indexを更新します。\nPython: %s\n\n' "$us_index_python"
"$us_index_python" -u run_all.py 2>&1 | tee "$us_index_log"
us_index_status=${PIPESTATUS[0]}

if [ "$us_index_status" -eq 0 ]; then
    printf '\n正常終了しました。\n'
else
    printf '\n更新は完了していません。上のエラーをご確認ください。\n'
fi
printf 'ログ: %s/%s\n' "$PWD" "$us_index_log"

if [ -t 0 ]; then
    read -r -p 'Enterキーで閉じます。' _
fi
exit "$us_index_status"
