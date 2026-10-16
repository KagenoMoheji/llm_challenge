# AGENTS.md

CaPass(AIエージェントのツール利用を判定・管理するCapability Gateway)のリポジトリです。

**コードを書く・直す・レビューする前に、必ず [`skills/capass-coding-conventions/SKILL.md`](skills/capass-coding-conventions/SKILL.md) を読み、従ってください。**
特に、`__init__.py` を除く全Pythonモジュールの冒頭に定型ヘッダを書くルール(エントリポイントだけ `ROOTPATH` を書く)があります。

- 構成: `server/`(RestAPIサーバ。Python3 / FastAPI / SQLAlchemy)、`cli/`(CaPassクライアント。未実装)、`examples/`(暫定クライアント)
- 使い方と登録の手順: [`QUICKSTART.md`](QUICKSTART.md)
- テスト: `cd server && pip install -e ".[dev]" && pytest`(必要な環境変数は QUICKSTART を参照)

> Claude Code に自動で読み込ませる場合は、スキルを `.claude/skills/` に置いてください(`mkdir -p .claude/skills && cp -r skills/capass-coding-conventions .claude/skills/`)。
