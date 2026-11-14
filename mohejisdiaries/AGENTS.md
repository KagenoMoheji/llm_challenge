# AGENTS.md - Moheji's Diaries 開発規約 & テストガイドライン

このドキュメントは、LLMコーディングエージェントおよび開発者が「Moheji's diaries（もへじの編綴）」Webアプリケーションの開発・保守・機能追加を行うためのアーキテクチャ方針、コーディング規約、およびテスト実行手順をまとめたものです。

他のLLM（ChatGPT, Claude, Cursor, Copilot 等）が作業を引き継ぐ際にも、本書に記載の規約とテストコマンドに従って開発を進めてください。

---

## 1. プロジェクト概要

「Moheji's diaries = もへじの編綴」は、GitHub Pages として公開される静的Webブログアプリケーションです。

- **フロントエンド構成**: HTML / CSS / JavaScript を `./index.html` のシングルファイルに統合した静的Webアプリ
  - ルーティング: トップページ（`?path` なし）、記事詳細（`/articles/{yyyy}/{採番}`）、404エラー（`/errors/404`）、記事プレビュー（`/articles/preview` ※直接URLアクセス専用）
- **データソース**:
  - 記事一覧テーブル: `https://raw.githubusercontent.com/KagenoMoheji/llm_challenge/db_mohejisdiaries/mohejisdiaries/github_actions/deliverable/tbl_articles/table.json` (`db_mohejisdiaries` ブランチ)
  - 個別記事データ: `https://raw.githubusercontent.com/KagenoMoheji/llm_challenge/main/mohejisdiaries/articles/{fileName}` (`main` ブランチの YAML ファイル)
- **CI/CD (GitHub Actions)**:
  - `./github_actions/tbl_articles/`: `main` ブランチの記事YAML追加・更新をトリガーに Python スクリプトで `table.json` を生成し、`db_mohejisdiaries` ブランチへコミットするワークフロー

---

## 2. コーディング規約 & 設計指針

### 2.1 状態管理（Redux風アーキテクチャ）
トップページのフィルタ条件（タグ、検索ワード）およびスライダーのページ番号は、**Redux風の単一状態ストア（Store / Reducer / Actions）** で管理します。

1. **Single Source of Truth**:
   - 状態は `topStore`（`createStore(topReducer, initialTopState)`）の内部でのみ保持し、直接の変数代入や分散したグローバル変数は作らないこと。
   - `topStore.getState()`, `topStore.dispatch(action)`, `topStore.subscribe(listener)` を通じてアクセスすること。
2. **Action Types & Action Creators**:
   - アクションはプレフィックス付き文字列（例: `top/SET_FILTER`, `top/SET_PAGE`, `top/SET_MOBILE_PAGE`, `top/RESET_STATE`, `top/RESTORE_STATE`）とし、Action Creators 経由で生成すること。
3. **純粋関数 Reducer**:
   - `topReducer(state, action)` は副作用を持たず、新しいイミュータブルな状態オブジェクトを返すこと。
   - フィルタ条件変更（`SET_FILTER`）時は、スライダーページ番号（`pageIndex`, `mobilePageIndex`）を自動的に `0` にリセットすること。
4. **画面遷移と状態の維持・復元**:
   - 記事詳細画面へ遷移する際、現在のトップページ状態（`topStore.getState()`）を `window.history.replaceState({ topState: ... }, '', ...)` で履歴エントリに保存すること。
   - ブラウザの「戻る」ボタン（`popstate` イベント）でトップに戻った場合のみ、保存された状態を `topStore.dispatch(actions.restoreState(...))` で復元し、スライダーのページ位置・タグ選択・検索ワード・ラベルを直前の状態へ戻すこと。
   - **ヘッダーリンク（「もへじの編綴」）やトップページへの明示的なリンクから遷移した場合は、必ず `actions.resetState()` を dispatch して初期状態（全件表示・先頭ページ）にリセットすること。**

### 2.2 GitHub API の完全排除と Raw URL の利用（レートリミット回避）
- **GitHub REST API (`api.github.com`) の直接呼び出しは厳禁**です（未認証アクセス時に 60回/時の厳しいレート制限があり、サイト閲覧時にエラーとなるため）。
- 記事一覧データの取得には、GitHub Actions が自動生成する `table.json`（Raw URL）を使用すること。
- 個別記事の YAML 取得時は、`table.json` から記事ID（`yyyyNNN`）に一致するレコードの `fileName` を取得し、`https://raw.githubusercontent.com/KagenoMoheji/llm_challenge/main/mohejisdiaries/articles/{fileName}` から直接 `fetch` して `jsyaml.load` すること。
- テーブルJSON取得関数（`getArticlesTable`）にはキャッシュ機構（キャッシュTTLとキャッシュバスター `?_t=...`）を設け、過剰なネットワークフェッチを防ぐこと。

### 2.3 CSS カスケードとレスポンシブ設計
- **ベーススタイルとメディアクエリの記述順序**:
  1. PC版（デスクトップ）向けの全ベーススタイル（レイアウト、スライダー、ウィジェット）を先に定義する。
  2. メディアクエリは必ず**ベーススタイルの後（末尾）**に、大きい画面から小さい画面の順序（降順）で定義すること：
     - タブレット版: `@media (max-width: 1200px)`
     - スマホ版: `@media (max-width: 855px)`
  3. *注意*: メディアクエリをベーススタイルより前に書いてしまうと、詳細度が同じセレクタ同士のカスケード順によりベーススタイルで上書きされてしまうため、必ず末尾にまとめること。
- **ブレークポイント**:
  - `1200px`: PC（右側サイドバー） ↔ タブレット（下回り込み・横2列上揃え）
  - `855px`: タブレット（タイル幅 285px × 3列 = 855px） ↔ スマホ（縦1列・10記事/ページ）

### 2.4 UI & タイル仕様
- **ナビタイルの表記**:
  - 全角スペースを含めること（例: `最　新<br>の<br>記　事`、`過　去<br>の<br>記事へ`、`最　近<br>の<br>記事へ`、`最　古<br>の<br>記　事`）。
- **タイルのサイズ**:
  - 幅 285px、高さ 500px。
- **空タイル**:
  - スライダー最終ページ等で記事が存在しない空タイル（`.empty-tile`）には境界線（`border`）を表示しないこと。
- **ホバーアニメーション**:
  - タイル境界線: 左下始点でアクセントカラー（`--accent: #d4532f`）に染まるアニメーション。
  - 「続きを読む」ボタン: ホバー時に「■」から右向き三角「■▶」が出現するアニメーション。
- **フッター**:
  - 上下左右中央配置（`display: flex; justify-content: center; align-items: center;`）で、`&copy;Copyright 2017 もへじの編綴. All rights reserved.` を表示すること。

---

## 3. テストの実行手順 (WSL2 + Docker ワンライナー)

ホストOSのローカル環境を汚さない方針のため、テスト・検証・コードチェックはすべて **WSL2 上の Docker コンテナ（使い捨て `--rm`）** でワンライナー実行します。

> **実行パスの注意点**:
> Windows（PowerShell）から実行する場合は、ユーザー名環境変数 `${env:USERNAME}` を使ってマウントします：
> `-v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/mohejisdiaries:/workspace`
> （※WSL bash 内から実行する場合は `$(pwd)` や `/mnt/c/Users/<user>/...` に適宜置き換えてください）

### 3.1 CSS 構文チェック
`index.html` 内の `<style>` タグに含まれる CSS の開き括弧 `{` と閉じ括弧 `}` の整合性を検証します。

```bash
wsl docker run --rm \
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/mohejisdiaries:/workspace \
  -w /workspace \
  node:20-alpine \
  node -e "
const fs = require('fs');
const html = fs.readFileSync('index.html', 'utf8');
const styleMatches = [...html.matchAll(/<style>([\s\S]*?)<\/style>/gi)];
console.log('Found', styleMatches.length, 'style blocks');
styleMatches.forEach((match, i) => {
    const css = match[1];
    const openBraces = (css.match(/\{/g) || []).length;
    const closeBraces = (css.match(/\}/g) || []).length;
    console.log('Style block', i + 1, 'Open braces:', openBraces, 'Close braces:', closeBraces);
    if (openBraces !== closeBraces) {
        console.error('Mismatch in CSS braces!');
        process.exit(1);
    }
});
console.log('CSS syntax validation passed!');
"
```

### 3.2 JavaScript 構文チェック (Syntax Validation)
`index.html` 内の `<script>` タグの JavaScript に文法エラー（SyntaxError）がないかを検証します。

```bash
wsl docker run --rm \
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/mohejisdiaries:/workspace \
  -w /workspace \
  node:20-alpine \
  node -e "
const fs = require('fs');
const html = fs.readFileSync('index.html', 'utf8');
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

### 3.3 状態管理（Redux Store）＆フロントエンド単体テスト
`index.html` 内の `topStore`（Action、Reducer、Store、フィルタ関数、復元・リセットロジック）を Node.js の VM コンテキスト上で実行し、アサーションテストを行います。

```bash
wsl docker run --rm \
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/mohejisdiaries:/workspace \
  -w /workspace \
  node:20-alpine \
  node -e "
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync('index.html', 'utf8');
const scriptMatch = html.match(/<script(?![^>]*src=)>([\s\S]*?)<\/script>/i);
if (!scriptMatch) { console.error('No script found'); process.exit(1); }

const testScript = scriptMatch[1] + \`
console.log('--- Running topStore Unit Tests ---');
// 1. 初期状態
let s = topStore.getState();
console.assert(s.filter.type === 'all' && s.pageIndex === 0 && s.mobilePageIndex === 0, 'Initial state failed');

// 2. タグフィルタ設定
topStore.dispatch(actions.setFilter('tag', 'Docker'));
s = topStore.getState();
console.assert(s.filter.type === 'tag' && s.filter.value === 'Docker' && s.pageIndex === 0, 'Tag filter failed');

// 3. ページ番号設定
topStore.dispatch(actions.setPage(2));
topStore.dispatch(actions.setMobilePage(3));
s = topStore.getState();
console.assert(s.pageIndex === 2 && s.mobilePageIndex === 3, 'Page set failed');

// 4. フィルタ変更時のページリセット
topStore.dispatch(actions.setFilter('search', 'Python'));
s = topStore.getState();
console.assert(s.pageIndex === 0 && s.filter.value === 'Python', 'Filter change page reset failed');

// 5. 履歴復元 (ページバック時)
topStore.dispatch(actions.restoreState({ filter: { type: 'tag', value: 'React' }, pageIndex: 1, mobilePageIndex: 2 }));
s = topStore.getState();
console.assert(s.filter.value === 'React' && s.pageIndex === 1 && s.mobilePageIndex === 2, 'Restore failed');

// 6. 初期化 (ヘッダークリック時)
topStore.dispatch(actions.resetState());
s = topStore.getState();
console.assert(s.filter.type === 'all' && s.pageIndex === 0, 'Reset failed');

// 7. フィルタ関数
const dummy = [{ title: 'A', tags: ['X'] }, { title: 'B', tags: ['Y'] }];
console.assert(filterArticles(dummy, { type: 'tag', value: 'X' }).length === 1, 'filterArticles tag failed');
console.assert(filterArticles(dummy, { type: 'search', value: 'b' }).length === 1, 'filterArticles search failed');

console.log('All Store unit tests passed successfully!');
\`;

const context = {
    console,
    window: { location: { search: '', pathname: '/' }, history: { pushState(){}, replaceState(){} }, addEventListener(){} },
    document: { createElement: () => ({ appendChild(){}, textContent: '' }), head: { appendChild(){} }, title: '', getElementById: () => null, querySelectorAll: () => [], querySelector: () => null },
    MonoMD: { getMonoMDCSS: () => '' },
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
};
vm.createContext(context);
vm.runInContext(testScript, context);
"
```

### 3.4 Python ユニット＆結合テスト (Pytest)
GitHub Actions で動作する記事テーブル生成スクリプト（`generate_table.py`）の単体・結合テストを実行します。

```bash
wsl docker run --rm \
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/mohejisdiaries:/workspace \
  -w /workspace \
  python:3.11-slim \
  sh -c "pip install --no-cache-dir -r github_actions/tbl_articles/requirements.txt && pytest github_actions/tbl_articles/test_generate_table.py -v"
```

### 3.5 Python テーブル生成ワンライナー実行
実際に YAML 群から `table.json` を生成するテスト実行コマンドです。

```bash
wsl docker run --rm \
  -v /mnt/c/Users/${env:USERNAME}/git/llm_challenge/main/llm_challenge/mohejisdiaries:/workspace \
  -w /workspace \
  python:3.11-slim \
  sh -c "pip install --no-cache-dir -r github_actions/tbl_articles/requirements.txt && python github_actions/tbl_articles/generate_table.py --articles-dir articles --output github_actions/deliverable/tbl_articles/table.json"
```

---

## 4. エージェント運用ルール (制約事項)

LLMエージェントが本リポジトリで作業を行う際は、以下のルールを厳守してください。

1. **Git ブランチ操作の禁止**:
   - ブランチの作成（`git checkout -b` 等）や切り替えはユーザー自身が行います。エージェント側でブランチ操作を行ってはなりません。
   - コミットログを遡って探索したり、上位ディレクトリへ探索を広げたりせず、指定されたカレントディレクトリ（`mohejisdiaries`）配下でのみ作業してください。
2. **ホスト環境の保護**:
   - ホストOS（Windows）環境に直接パッケージをインストールしたり環境変数を書き換えたりせず、コマンド実行は WSL2 Docker コンテナ（`--rm`）を活用してください。
3. **シングルファイル構成の維持**:
   - Webアプリ本体はシングルファイル `./index.html` として完結している必要があります。JSやCSSを安易に別ファイルへ分離せず、`index.html` 内で整合性を維持して改修してください。
