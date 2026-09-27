#!/bin/bash
set -o pipefail
cd -- "$(dirname -- "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
printf '\n現在の楽天フォルダをGitHubへ更新\n\n'
if [ -x .venv/bin/python ]; then
    rakuten_python=.venv/bin/python
else
    rakuten_python=python3
fi
mkdir -p .logs || exit 1
rakuten_log=".logs/update-$(date +%Y%m%d-%H%M%S)-$$.log"
"$rakuten_python" -u update_rakuten_github.py "$@" 2>&1 | tee "$rakuten_log"
rakuten_status=${PIPESTATUS[0]}
if [ "$rakuten_status" -eq 0 ]; then
    printf '\n正常終了しました。\n'
else
    printf '\n更新は完了していません。上のエラーをご確認ください。\n'
fi
printf 'ログ: %s/%s\n' "$PWD" "$rakuten_log"
if [ -t 0 ]; then
    read -r -p 'Enterキーで閉じます。' _
fi
exit "$rakuten_status"
