# AGENTS.md

CaPass(AIエージェントのツール利用を判定・管理するCapability Gateway)のリポジトリです。

**コードを書く・直す・レビューする前に、必ず [`skills/capass-coding-conventions/SKILL.md`](skills/capass-coding-conventions/SKILL.md) を読み、従ってください。**
特に、`__init__.py` を除く全Pythonモジュールの冒頭に定型ヘッダを書くルール(エントリポイントだけ `ROOTPATH` を書く)があります。

- 構成: `core/`(共通部品と `capass` コマンド。パッケージ `capass_core`)、`server/daemon/`(RestAPIサーバ。Python3 / FastAPI / SQLAlchemy。パッケージ `capass_server`)、`toolserver/`(ツールサーバのモード。パッケージ `capass_toolserver`)、`agent/`(AIエージェントのモード。パッケージ `capass_agent`)、`examples/`(暫定クライアント)。モードごとに、別のパッケージで、1つのサーバに1つだけインストールする(詳しくは SKILL.md の 2. と 11.)
- 使い方と登録の手順: [`QUICKSTART.md`](QUICKSTART.md)
- 未実装・検討事項: [`docs/TODO.md`](docs/TODO.md)
- テスト(プロジェクトごとに実行する): `cd server/daemon && pip install -e ".[dev]" && pytest`(必要な環境変数は QUICKSTART を参照)。`core`、`toolserver`、`agent` は、`pip install -e ./core -e "./toolserver[dev]"` のようにインストールして、各ディレクトリで `pytest`。**モードのパッケージ(`toolserver` `agent` `server/daemon`)は、同じPython環境に、複数インストールしない**(`capass` コマンドが、エラーにする)。モードごとに、別のvenvを使う

> Claude Code に自動で読み込ませる場合は、スキルを `.claude/skills/` に置いてください(`mkdir -p .claude/skills && cp -r skills/capass-coding-conventions .claude/skills/`)。
