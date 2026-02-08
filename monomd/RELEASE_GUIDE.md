# MonoMD - npm リリース手順書

## パッケージ情報

- **パッケージ名**: monomd
- **バージョン**: 1.0.0
- **説明**: A redundant-free Markdown parser where every symbol has its own unique role.
- **ライセンス**: MIT

## 🎯 MonoMDの特徴

MonoMDは、各記号が独自の役割を持つ、冗長性のないマークダウンパーサです。
従来のMarkdownパーサとは異なり、同じ機能を表現する複数の記法を排除しています。

### 記号の役割

- `**text**` = 太字 (Bold)
- `__text__` = 下線 (Underline) ※イタリックではありません!
- `~~text~~` = 取り消し線 (Strikethrough)
- `` `code` `` = インラインコード
- `![alt](url)` = 画像 + キャプション
- `!!text!!(path)` = 内部リンク
- `- [ ]` / `- [x]` = チェックボックス
- `:::info` / `:::warn` / `:::alert` = インフォメーションブロック
- ` ```code\n:::output\n... ` = コード + 出力セクション
- `| header |[caption]` = テーブル + キャプション

## ファイル構成

```
monomd/
├── index.js              # メインパーサコード
├── package.json          # パッケージ設定
├── README.md             # 使用方法とドキュメント
├── CHANGELOG.md          # 変更履歴
├── LICENSE               # MITライセンス
├── RELEASE_GUIDE.md      # このファイル
├── test.js               # テストスイート (20テスト)
├── example.html          # ブラウザデモ
├── .gitignore            # Git除外設定
└── .npmignore            # npm除外設定
```

## リリース前の確認事項

### ✅ 1. テストの実行

```bash
cd /home/claude/monomd
node test.js
```

すべてのテストが成功することを確認してください（20/20テストがパス）。

### ✅ 2. パッケージ内容の確認

```bash
npm pack --dry-run
```

パッケージに含まれるファイルを確認します。

### ✅ 3. ローカルでのインストールテスト

```bash
npm pack
npm install -g monomd-1.0.0.tgz
```

### ✅ 4. package.json の確認

以下の項目が正しく設定されていることを確認：
- ✅ name: "monomd"
- ✅ version: "1.0.0"
- ✅ description: "A redundant-free Markdown parser where every symbol has its own unique role."
- ✅ main: "index.js"
- ✅ keywords: 適切なキーワード
- ✅ license: "MIT"

## npmへの公開手順

### 1. npmアカウントの準備

npmアカウントを持っていない場合は、https://www.npmjs.com/ で作成してください。

### 2. npmにログイン

```bash
npm login --auth-type legacy
```

ユーザー名、パスワード、メールアドレスを入力します。

### 3. パッケージ名の確認

パッケージ名が利用可能か確認：

```bash
npm view monomd
```

エラーが表示される場合は、その名前は利用可能です。

### 4. パッケージの公開

```bash
cd /home/claude/monomd
npm publish --auth-type legacy
```

### 5. 公開の確認

```bash
npm view monomd
```

または https://www.npmjs.com/package/monomd にアクセスして確認します。

## 公開後の作業

### 1. GitHubリポジトリの作成

1. GitHubで新しいリポジトリを作成
2. リポジトリURLをコピー

### 2. package.jsonの更新

```json
{
  "repository": {
    "type": "git",
    "url": "https://github.com/yourusername/monomd.git"
  },
  "bugs": {
    "url": "https://github.com/yourusername/monomd/issues"
  },
  "homepage": "https://github.com/yourusername/monomd#readme"
}
```

### 3. コードをGitHubにプッシュ

```bash
git init
git add .
git commit -m "Initial commit - MonoMD v1.0.0"
git branch -M main
git remote add origin https://github.com/yourusername/monomd.git
git push -u origin main
```

### 4. タグの作成

```bash
git tag v1.0.0
git push --tags
```

## バージョンアップ手順

### パッチアップデート（バグ修正）

```bash
# CHANGELOG.mdを更新
npm version patch  # 1.0.0 → 1.0.1
npm publish
git push --tags
```

### マイナーアップデート（新機能追加）

```bash
# CHANGELOG.mdを更新
npm version minor  # 1.0.0 → 1.1.0
npm publish
git push --tags
```

### メジャーアップデート（破壊的変更）

```bash
# CHANGELOG.mdを更新
npm version major  # 1.0.0 → 2.0.0
npm publish
git push --tags
```

## トラブルシューティング

### パッケージ名が既に使用されている場合

1. package.jsonのnameを変更（例: `@yourusername/monomd`）
2. スコープ付きパッケージとして公開：
   ```bash
   npm publish --access public
   ```

### 公開に失敗した場合

```bash
# npmのキャッシュをクリア
npm cache clean --force

# 再度ログイン
npm logout
npm login

# 再度公開
npm publish
```

## 使用例

### インストール

```bash
npm install monomd
```

### Node.jsでの使用

```javascript
const { renderMarkdown } = require('monomd');

const markdown = `
# Hello MonoMD

This is **bold** and this is __underlined__.
`;

renderMarkdown(markdown).then(result => {
  console.log(result.html);      // HTMLのみ
  console.log(result.css);       // CSSのみ
  console.log(result.fullHTML);  // HTML + CSS
});
```

### ブラウザでの使用

```html
<script src="node_modules/monomd/index.js"></script>
<script>
  MonoMD.renderMarkdown('# Hello').then(result => {
    // CSSを追加
    document.head.insertAdjacentHTML('beforeend', `<style>${result.css}</style>`);
    // HTMLを表示
    document.getElementById('output').innerHTML = result.html;
  });
</script>
```

## 主な機能

### 1. 冗長性のない記法

MonoMDでは、各記号が独自の役割を持ちます：
- `**bold**` = 太字
- `__underline__` = 下線（イタリックではない！）
- これにより、混乱がなく明確なマークダウンを書けます

### 2. 独自の拡張機能

- 内部リンク: `!!text!!(path)`
- コード出力: ` ```\n:::output\n... `
- テーブルキャプション: `|header|[caption]`
- インフォブロック: `:::info`, `:::warn`, `:::alert`

### 3. CSSが含まれる

生成されるHTMLには`.monomd-body`クラスが付与され、
専用のCSSが提供されるため、すぐに美しく表示できます。

## サポート

- **Issues**: GitHubのIssuesページで報告してください
- **Pull Requests**: 歓迎します！
- **ドキュメント**: README.mdを参照してください

## ライセンス

MIT License

---

**作成日**: 2026-02-07
**MonoMD v1.0.0**
**A redundant-free Markdown parser where every symbol has its own unique role.**