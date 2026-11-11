# Testindmap - 開発者向けドキュメント (Developer Guide)

本ドキュメントは、Testindmap VSCode拡張機能の開発・ビルド・デバッグを行う開発者向けのメモです。

---

## 💡 特徴・環境構築について（Node.js等のインストール不要）

- **PCへのプログラミング言語インストールは一切不要です**
  - エントリポイント（`extension.js`）およびWebview（UI）はすべて **Vanilla JS（純粋なJavaScript / CommonJS）** で実装されています。
  - TypeScriptコンパイラ（`tsc`）やWebpack等のビルド/トランスパイル環境の構築は不要です。
  - VS Code自身が内包しているNode.jsランタイムによって直接実行されます。
- **完全オフライン対応**
  - マークダウンレンダラ `monomd`（v1.0.1）を `media/monomd.js` に同梱しているため、インターネット環境のない隔離環境・社内ネットワークでも安定して動作します。

---

## 🚀 動作確認・デバッグ方法（F5キーを押すだけ）

VS Codeさえインストールされていれば、今すぐ動作確認が可能です。

1. VS Codeで `vscode-ext` フォルダを開きます。
2. キーボードの **`F5`** キーを押す（または「実行とデバッグ」パネルから **「Testindmap拡張機能を実行」** をクリック）。
3. 自動的に「拡張機能開発ホスト」の新しいVS Codeウィンドウが立ち上がります。
4. 新しいウィンドウで以下のいずれかを実行してください：
   - `sample.testmap.json` をクリックして開く
   - コマンドパレット（`Ctrl+Shift+P`）を開き、`Testindmap: 新規テスト仕様書マインドマップを作成` を実行

---

## 📦 Dockerを使った `.vsix` パッケージ化手順

WSL2上のDockerを使って、ホストPCにNode.jsを一切入れずに `.vsix` ファイル（拡張機能パッケージ）を生成し、`vscode-ext/dist/` に出力できます。

**WSL2 / Linuxターミナルで実行:**
```bash
cd /path/to/testindmap/vscode-ext

# testindmap-vscode-ext でビルドし、親直下の dist/ に出力
docker run --rm -v "$(pwd):/app" -w /app/testindmap-vscode-ext node:20-alpine npx @vscode/vsce package --allow-missing-repository -o /app/dist/
```

**Windows PowerShellで実行:**
```powershell
wsl docker run --rm -v /mnt/$HOME/git/llm_challenge/main/llm_challenge/testindmap/vscode-ext:/app -w /app/testindmap-vscode-ext node:20-alpine npx @vscode/vsce package --allow-missing-repository -o /app/dist/
```

※パッケージ化コマンドを実行する際、ソースコード外の `vscode-ext/dist/` に出力されるため、`vsce` のパッケージ自己巻き込み事故（前回の `.vsix` を取り込んでサイズが肥大化する問題）を防ぐことができます。

---

## 📁 ディレクトリ構成

```text
vscode-ext/
├── DEVELOPMENT.md               # 本開発者向けドキュメント
├── sample.testmap.json          # 動作確認用サンプルデータ
├── .vscode/
│   └── launch.json              # F5デバッグ用設定
├── dist/                        # パッケージング済みファイル（配布用）
│   └── testindmap-0.1.0.vsix
└── testindmap-vscode-ext/       # 拡張機能本体（~/.vscode/extensions/配置用）
    ├── package.json             # 拡張機能定義マニフェスト
    ├── extension.js             # メインプロセス（CustomTextEditorProvider、Vanilla JS）
    ├── README.md                # VSCode画面上の拡張機能説明書（エンドユーザー向け）
    └── media/
        ├── app.html             # Webview HTMLテンプレート
        ├── app.css              # スタイルシート
        ├── app.js               # マインドマップUIロジック（VSCodeメッセージング統合）
        └── monomd.js            # マークダウンレンダラ（ローカル同梱）
```
