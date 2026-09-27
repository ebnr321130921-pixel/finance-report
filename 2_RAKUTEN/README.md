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
- `holdings_reconciliation.json`: Local user-reported balance and withdrawal record, including holdings before adjustment. Not a market-price source or part of the default publish set.
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

### 2026-09-27 holding adjustment

iFreeNASDAQ100 was reduced from 116,303 to 50,436 units after a reported
380,000 yen withdrawal. Its remaining `change_value` is provisionally allocated
as `630000 * 50436 / 116303`, rather than treating the withdrawal as a loss.
iDeCo units were updated to 24,833,799; the contribution amount is unknown,
so its original principal was retained. SOX and Rakuten QQQ NISA units match
the existing lots. The reported balances and original inputs are preserved in
`holdings_reconciliation.json`; valuation and transaction dates are unconfirmed.
The viewer continues to use fetched NAV, not the reported balance amounts.
Its historical account charts apply current holdings to past prices and are
not cash-flow-adjusted realized performance.

## Publish Local Holdings To GitHub

### ダブルクリックでフォルダを更新

Finderで **`楽天をGitHubへ更新.command`** をダブルクリックします。
現在のローカルフォルダを `ebnr321130921-pixel/finance-report` の
`main` ブランチ、`2_RAKUTEN/` に反映します。価格取得は行いません。
価格も更新したい場合は、先に通常どおり `rakuten_update.py` を実行してください。

初回だけ、GitHub認証がなければTerminal内でトークン登録を案内します。
[GitHubのトークン作成画面](https://github.com/settings/personal-access-tokens/new)で
対象リポジトリを `finance-report`、Repository permissionsのContentsを
`Read and write` にして作成し、password欄へ貼り付けます。
認証情報はMacのキーチェーンに保存し、2回目から再利用します。
既存の `GITHUB_TOKEN` / `GH_TOKEN`、またはGitHub CLIの認証も利用できます。
トークン更新時は「キーチェーンアクセス」で `rakuten-github-publisher` の
対象リポジトリの項目を削除し、再実行してください。

コード、保有データ、`daily_records.json`、`dashboard.html`、サブフォルダ内の
ファイルも対象です。`.venv`、キャッシュ、ログ、認証ファイル、ローカル用の
`holdings.private.json` / `holdings_reconciliation.json` は除外します。
GitHub側のフォルダを先に削除する必要はありません。同名ファイルを更新し、
新規ファイルを追加します。ローカルにないGitHub上のファイルは削除しません。
GitHub通信にはPython環境付属のCA証明書を明示的に使用するため、macOS上の
Pythonでシステム証明書が見つからない場合でも接続できます。
変更のあったファイルを1コミットで反映し、変更がなければコミットを作りません。
送信中にGitHub側が更新された場合は強制上書きせず停止するので、再実行してください。
この動作はGitHubの[Git Trees API](https://docs.github.com/en/rest/git/trees)と
[References API](https://docs.github.com/en/rest/git/refs)を使用します。

結果とエラーはTerminalに表示し、`.logs/` に保存します。
送信なしの確認は `./楽天をGitHubへ更新.command --dry-run` で実行できます。
任意で `--refresh` を付けると価格取得・画面生成後に送信します。

### コマンドから選択ファイルを送信

従来の選択ファイル送信も利用できます:

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
