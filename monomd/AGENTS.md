# AGENTS.md

このリポジトリ（`monomd`）で作業するAIエージェントおよび開発者のためのガイドラインとテスト実行手順書です。

---

## 1. プロジェクト概要

MonoMD は「各記号が一意の役割を持ち、構文の冗長性を排除した」独自のMarkdownパーサーです。
（例：イタリック等の表記揺れを排し、`**text**` は太字、`__text__` は下線、`~~text~~` は取り消し線、`` `code` `` はインラインコード等、各記号に固有の役割を割り当てています。）

### ディレクトリ構成
- `workspace/index.js` : MonoMD のコアロジック（Node.js / ブラウザ両対応の UMD 形式）
- `workspace/test.js` : 単体テストスイート（Node.js で実行）
- `workspace/sample.html` : ブラウザ上での動作確認・プレビュー用デモHTML
- `workspace/package.json` : npm パッケージ定義

---

## 2. WSL2 と Docker を利用したテスト実行（ワンライナー）

ローカル環境を汚さずに `node:20-alpine` コンテナを用いて安全かつ再現性高くテスト・検証を実行するためのワンライナー集です。
PowerShell から実行する場合は行末をバッククォート（`` ` ``）で繋ぎます。

### 2.1 単体テスト（test.js）の実行
`workspace/test.js` に定義された全テストケースを実行します。

```powershell
wsl docker run --rm `
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/monomd/workspace:/workspace `
  -w /workspace `
  node:20-alpine `
  node test.js
```

### 2.2 HTML内のインラインスクリプト構文検証
`sample.html`（または `index.html`）内の `<script>` タグに含まれるJavaScriptの構文エラーがないかを検証します。

```powershell
wsl docker run --rm `
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/monomd/workspace:/workspace `
  -w /workspace `
  node:20-alpine `
  node -e "
const fs = require('fs');
const html = fs.readFileSync('sample.html', 'utf8');
const scriptMatches = [...html.matchAll(/<script(?![^>]*src=)>([\s\S]*?)<\/script>/gi)];
console.log('Found', scriptMatches.length, 'inline scripts');
scriptMatches.forEach((match, i) => {
    try {
        new Function(match[1]);
        console.log('Script block', i + 1, 'syntax OK');
    } catch (e) {
        console.error('Script block', i + 1, 'syntax error:', e.message);
        process.exit(1);
    }
});
console.log('JavaScript syntax validation passed!');
"
```

### 2.3 個別の機能検証（例: インラインコードのHTMLタグエスケープ確認）
特定の入力値に対するパーサーの挙動を直接検証するワンライナーです。

```powershell
wsl docker run --rm `
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/monomd/workspace:/workspace `
  -w /workspace `
  node:20-alpine `
  node -e "
const { renderMarkdown, parseInline } = require('./index.js');
const bt = String.fromCharCode(96);
const input = bt + '<iframe>' + bt;
console.log('parseInline:', parseInline(input));
renderMarkdown(input).then(r => console.log('renderMarkdown:', r.html));
"
```

---

## 3. 実装上の注意事項

1. **インラインコードのエスケープ**:
   - インラインコード（`` `code` ``）内の文字列は `escapeHtml` を通す必要があります。
   - `<iframe>` や `<script>` などのHTMLタグがそのまま渡ると、ブラウザ描画時にHTMLとして解釈されてレイアウト崩れやXSSの原因となるため、`<code>&lt;iframe&gt;</code>` のようにエスケープされる仕様となっています。

2. **コードブロックのキャプション**:
   - ```` ```[キャプション] ```` または ```` ```lang[キャプション] ```` の形式で指定された角括弧内のテキストは、コードブロック（または出力付きコードブロックコンテナ）の直下に `<div class="code-caption">` として出力されます。
   - キャプション内の文字列は `escapeHtml` でエスケープされ、テーブルの `caption` と同様に中央揃え（`text-align: center;`）でスタイリングされます。

3. **インデントされたコードブロックの処理**:
   - 箇条書きの折り返し行などに配置されたインデント付きコードブロック（例: `  ``` `）では、開始行のインデント幅（`indent`）を取得し、コードブロック内の各行の先頭からそのインデント幅分を除去します。
   - これにより、コードブロック1行目だけでなく2行目以降も余分なインデントがつかず、コード本来のインデントが正確に保持されます。

4. **Node.js とブラウザのハイブリッド対応**:
   - `escapeHtml` はブラウザ環境（`typeof document !== 'undefined'`）では DOM 要素を使い、Node.js 環境では正規表現置換でエスケープを行います。
   - モジュールエクスポートは CommonJS（`module.exports`）とブラウザ用グローバル（`window.MonoMD`）の両方に対応しています。
