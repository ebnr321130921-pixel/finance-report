#!/bin/bash
set -o pipefail

cd -- "$(dirname -- "$0")" || exit 1

us_index_python=""
for candidate in \
    .venv/bin/python \
    "$HOME/.pyenv/versions/3.10.6/bin/python3" \
    "$HOME/.pyenv/versions/3.14.4/bin/python3"
do
    if [ -x "$candidate" ] && "$candidate" -c 'import certifi' >/dev/null 2>&1; then
        us_index_python=$candidate
        break
    fi
done

if [ -z "$us_index_python" ]; then
    printf '利用可能なPython環境がありません。先に「US指数を更新.command」を実行してください。\n'
    exit 1
fi

mkdir -p .logs || exit 1
us_index_log=".logs/github-$(date +%Y%m%d-%H%M%S)-$$.log"

printf '\n現在の3_US_IndexフォルダをGitHubへ同期します。\n\n'
"$us_index_python" -u publish_us_index_to_github.py "$@" 2>&1 | tee "$us_index_log"
us_index_status=${PIPESTATUS[0]}

if [ "$us_index_status" -eq 0 ]; then
    printf '\n正常終了しました。\n'
else
    printf '\nGitHub更新は完了していません。上のエラーをご確認ください。\n'
fi
printf 'ログ: %s/%s\n' "$PWD" "$us_index_log"

if [ -t 0 ]; then
    read -r -p 'Enterキーで閉じます。' _
fi
exit "$us_index_status"
