# datlinx - 開発者向けドキュメント (Developer Guide)

本ドキュメントは、datlinx VSCode拡張機能の開発・ビルド・デバッグを行う開発者向けのメモです。

---

## 💡 特徴・環境構築について（Node.js等のインストール不要）

- **PCへのプログラミング言語・ビルドツールのインストールは一切不要です**
  - エントリポイント（`extension.js`）およびWebview（UI）はすべて **Vanilla JS（純粋なJavaScript / CommonJS）** で実装されています。
  - TypeScriptコンパイラ（`tsc`）やWebpack等のビルド/トランスパイル環境の構築は不要です。
  - VS Code自身が内包しているNode.jsランタイムによって直接実行されます。
- **完全オフライン対応**
  - 外部CDNやネットワーク接続を一切必要とせず、隔離環境・社内ネットワークでも軽快に動作します。

---

## 🚀 動作確認・デバッグ方法（F5キーを押すだけ）

VS Codeさえインストールされていれば、今すぐ動作確認が可能です。

1. VS Codeで `vscode-ext` フォルダを開きます。
2. キーボードの **`F5`** キーを押す（または「実行とデバッグ」パネルから **「datlinx拡張機能を実行」** をクリック）。
3. 自動的に「拡張機能開発ホスト」の新しいVS Codeウィンドウが立ち上がります。
4. 新しいウィンドウで以下のいずれかを実行してください：
   - コマンドパレット（`Ctrl+Shift+P`）を開き、`datlinx: サンプルSQLデータで開く` を実行
   - エクスプローラーで任意のSQLフォルダを右クリックし、`datlinx: SQLフォルダを解析してマインドマップを開く` を実行
   - コマンドパレットから `datlinx: ワークスペースの全SQLを解析して開く` を実行

---

## 📦 Dockerを使った `.vsix` パッケージ化手順

WSL2上のDockerを使って、ホストPCにNode.jsを一切入れずに `.vsix` ファイル（拡張機能パッケージ）を生成し、`vscode-ext/dist/` に出力できます。

**WSL2 / Linuxターミナルで実行:**
```bash
cd /path/to/datlinx/vscode-ext

# datlinx-vscode-ext でビルドし、親直下の dist/ に出力
docker run --rm -v "$(pwd):/app" -w /app/datlinx-vscode-ext node:20-alpine npx @vscode/vsce package --allow-missing-repository -o /app/dist/
```

**Windows PowerShellで実行:**
```powershell
wsl docker run --rm -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/datlinx/vscode-ext:/app -w /app/datlinx-vscode-ext node:20-alpine npx @vscode/vsce package --allow-missing-repository -o /app/dist/
```

※パッケージ化コマンドを実行する際、ソースコード外の `vscode-ext/dist/` に出力されるため、`vsce` のパッケージ自己巻き込み事故（前回の `.vsix` を取り込んでサイズが肥大化する問題）を防ぐことができます。

---

## 📥 生成された `.vsix` のインストール方法

`vscode-ext/dist/datlinx-0.1.0.vsix` は以下の方法でVS Codeへ直接インストールできます：

1. **VS Code GUIから**:
   - サイドバーの「拡張機能」アイコン（`Ctrl+Shift+X`）をクリック
   - 右上の「`…`」（その他の操作メニュー）→「**VSIXからのインストール... (Install from VSIX...)**」を選択
   - `vscode-ext/dist/datlinx-0.1.0.vsix` を選択
2. **CLIから**:
   ```bash
   code --install-extension vscode-ext/dist/datlinx-0.1.0.vsix
   ```

---

## 📁 ディレクトリ構成

```text
vscode-ext/
├── DEVELOPMENT.md               # 本開発者向けドキュメント
├── .vscode/
│   └── launch.json              # F5デバッグ用設定
├── dist/                        # パッケージング済みファイル（配布用）
│   └── datlinx-0.1.0.vsix       # 生成された拡張機能パッケージ (VSIX)
└── datlinx-vscode-ext/          # 拡張機能本体（~/.vscode/extensions/配置用）
    ├── package.json             # 拡張機能定義マニフェスト
    ├── extension.js             # メインプロセス（WebviewPanel管理、Vanilla JS）
    ├── README.md                # VSCode画面上の拡張機能説明書（エンドユーザー向け）
    └── media/
        ├── icon.svg             # 拡張機能アプリアイコン
        ├── app.html             # Webview HTMLテンプレート
        ├── app.css              # スタイルシート（ノードマージン・3色ハイライト）
        └── app.js               # マインドマップUIロジック（VSCodeメッセージング統合）
```
