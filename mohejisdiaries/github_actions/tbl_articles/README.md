# Articles Table Generator (`tbl_articles`)

`main` ブランチの `./articles/[0-9]{7}_.+.yml` から記事メタデータを抽出し、`db_mohejisdiaries` ブランチの `./github_actions/deliverable/tbl_articles/table.json` に反映する GitHub Actions ワークフローおよび Python スクリプトです。

## ディレクトリ構成

```
github_actions/
├── deliverable/
│   └── tbl_articles/
│       └── table.json                               # 生成された記事一覧テーブル (JSON)
└── tbl_articles/
    ├── README.md                                    # 本ドキュメント
    ├── generate_table.py                            # テーブル生成 Python スクリプト
    ├── requirements.txt                             # 依存パッケージ定義 (PyYAML, pytest)
    ├── test_generate_table.py                       # ユニット・結合テストコード
    └── mohejisdiaries_update_tbl_articles.yml       # GitHub Actions ワークフロー定義 ※`<repository>/.github/workflows/`に配置する
```

## `table.json` のレコード仕様

各レコードは以下のフィールドを持ちます：

```json
[
  {
    "id": "2019001",
    "fileName": "2019001_sample.yml",
    "title": "matplotlibでガントチャートを実装する",
    "createDate": "2019-07-13",
    "updateDate": "2019-07-13",
    "tags": [
      "Python",
      "個人開発"
    ]
  }
]
```

- `id`: ファイル名の先頭7桁（年4桁 + 番号3桁）
- `fileName`: YAMLファイル名
- `title`: 記事のタイトル
- `createDate`: 作成日（`YYYY-MM-DD` 形式に正規化）
- `updateDate`: 更新日（`YYYY-MM-DD` 形式に正規化、未指定時は `createDate` をフォールバック）
- `tags`: タグ一覧の文字列配列

## スクリプトの実行方法

### ローカル環境での実行
```bash
python generate_table.py \
  --articles-dir articles \
  --output github_actions/deliverable/tbl_articles/table.json
```

### WSL2 + Docker を使ったワンライナー実行 (ローカル環境を汚さない方法)
ホストOSのPython環境を変更せず、WSL2上のDockerコンテナ（使い捨て `--rm`）内で依存解決から実行までをワンライナーで行う手順です。

#### 1. テーブル生成
```bash
wsl docker run --rm \
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/mohejisdiaries:/workspace \
  -w /workspace \
  python:3.11-slim \
  sh -c "pip install --no-cache-dir -r github_actions/tbl_articles/requirements.txt && python github_actions/tbl_articles/generate_table.py --articles-dir articles --output github_actions/deliverable/tbl_articles/table.json"
```

#### 2. ユニットテスト実行
```bash
wsl docker run --rm \
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/mohejisdiaries:/workspace \
  -w /workspace \
  python:3.11-slim \
  sh -c "pip install --no-cache-dir -r github_actions/tbl_articles/requirements.txt && pytest github_actions/tbl_articles/test_generate_table.py -v"
```

### オプション引数
- `--articles-dir`: 記事YAMLファイルを探索するディレクトリ（デフォルト: `articles`）
- `--output`: 出力先JSONファイルパス（デフォルト: `github_actions/deliverable/tbl_articles/table.json`）
- `--sort-by`: ソート対象のキー（`createDate`, `updateDate`, `id`, `title`。デフォルト: `createDate`）
- `--order`: ソート順（`desc`: 降順, `asc`: 昇順。デフォルト: `desc`）

## テストの実行方法
```bash
pytest github_actions/tbl_articles/test_generate_table.py -v
```

## GitHub Actions ワークフロー (`mohejisdiaries_update_tbl_articles.yml`)

- **トリガー**: `main` ブランチへの push（PRマージ含む）時、`articles/**` または `github_actions/tbl_articles/**` の変更を検知
- **動作**:
  1. `main` ブランチ（記事ソース）をチェックアウト
  2. `db_mohejisdiaries` ブランチ（成果物保存先）をチェックアウト
  3. Python 環境をセットアップし、テストを実行
  4. `generate_table.py` で `table.json` を生成
  5. 差分がある場合、`db_mohejisdiaries` ブランチに自動コミット＆プッシュ
