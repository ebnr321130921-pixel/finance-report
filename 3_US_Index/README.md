# US Index Forecast Viewer

米国市場データを取得し、市場状態・回帰予測・Aegis Sigma診断を更新して
`us_index.html` を生成します。

## Macで更新する

Finderから `US指数を更新.command` をダブルクリックしてください。
利用可能なPython環境を自動選択し、ライブラリがなければ初回だけ
`.venv` を作って `requirements.txt` をインストールします。

Terminalから実行する場合:

```bash
./US指数を更新.command
```

現在のMacでは、依存ライブラリが導入済みの次のPythonでも実行できます。

```bash
/Users/satoshiito/.pyenv/versions/3.10.6/bin/python3 run_all.py
```

`/usr/local/bin/python3` など別のPythonを直接使う場合は、その環境へ先に
依存ライブラリを導入してください。

```bash
/usr/local/bin/python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run_all.py
```

## 処理順

1. Yahoo Financeから全必須銘柄を取得
2. データの完全性と鮮度を検証して安全にCSVを更新
3. 市場状態と予測を計算
4. 実行日時点の予測を評価ログへ追記
5. Aegis Sigma、集計CSV、`us_index.html` を生成

部分的な銘柄取得、古いデータ、欠損データの場合は、既存の正常な
`market_factors_raw.csv` を上書きせず停止します。

## 予測評価について

`walk_forward_v2` 以降、評価ログは実行日時点の予測だけを保存します。
同日の再実行で過去予測を書き換えません。旧方式のログは初回移行時に
`forecast_evaluation_log.legacy_pre_walk_forward.csv` へ退避されますが、
未来情報が混じるため評価やViewerには使用しません。

履歴の蓄積前は、Aegis Sigma欄に履歴蓄積中と表示されます。

## GitHubへ含めるもの

Pythonコード、`requirements.txt`、`README.md`、`.gitignore`、
`US指数を更新.command` を登録してください。`.venv`、キャッシュ、ログ、
旧方式の退避ログは `.gitignore` で除外されます。

### ダブルクリックでGitHubへ同期

Finderから `US指数をGitHubへ更新.command` をダブルクリックすると、現在の
フォルダを `ebnr321130921-pixel/finance-report` の `main` ブランチにある
`3_US_Index/` へ同期します。

初回のみGitHubトークンの登録を案内します。対象リポジトリを
`finance-report`、Repository permissionsのContentsを `Read and write` に
し、Workflowsも `Read and write` にしてください。Actions設定も更新するため、
Contents権限だけの楽天フォルダ用トークンとは分けて登録します。

送信せず対象ファイルだけを確認する場合:

```bash
./US指数をGitHubへ更新.command --dry-run
```

市場データ更新とViewer再生成も先に行う場合:

```bash
./US指数をGitHubへ更新.command --refresh
```

GitHub側だけに残っている `__pycache__`、`.pyc`、`.DS_Store` などは同期時に
削除されます。ローカルの `.venv`、ログ、認証情報は送信されません。

同期時には、リポジトリルートの `requirements.txt` と
`.github/workflows/daily_update.yml` も `github_root/` の管理版から更新します。
Actionsは `3_US_Index/run_all.py` を実行し、不足していた
`pandas-market-calendars` もインストールします。
