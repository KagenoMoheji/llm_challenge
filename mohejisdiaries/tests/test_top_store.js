const fs = require('fs');
const vm = require('vm');
const path = require('path');

// index.html の読み込み
const htmlPath = path.resolve(__dirname, '../index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

// インラインスクリプトを抽出
const scriptMatches = [...html.matchAll(/<script(?![^>]*src=)>([\s\S]*?)<\/script>/gi)];
if (scriptMatches.length === 0) {
    console.error('No inline script found in index.html');
    process.exit(1);
}
const scriptContent = scriptMatches.map(m => m[1]).join('\n');

const testCode = `
console.log('=== Running test_top_store.js ===');

// 1. 初期状態テスト
let s = topStore.getState();
console.assert(s.filter.type === 'all' && s.pageIndex === 0 && s.mobilePageIndex === 0, 'Initial state mismatch');

// 2. タグフィルタのアクション発火
topStore.dispatch(actions.setFilter('tag', 'Docker'));
s = topStore.getState();
console.assert(s.filter.type === 'tag' && s.filter.value === 'Docker' && s.pageIndex === 0, 'Tag filter dispatch failed');

// 3. ページインデックスの変更
topStore.dispatch(actions.setPage(3));
topStore.dispatch(actions.setMobilePage(4));
s = topStore.getState();
console.assert(s.pageIndex === 3 && s.mobilePageIndex === 4, 'Page change failed');

// 4. 検索フィルタ設定時のページ自動リセット (0に戻る)
topStore.dispatch(actions.setFilter('search', 'Python'));
s = topStore.getState();
console.assert(s.pageIndex === 0 && s.mobilePageIndex === 0 && s.filter.value === 'Python', 'Filter change did not reset page');

// 5. 履歴復元 (popstate / 戻るボタン押下時)
topStore.dispatch(actions.restoreState({ filter: { type: 'tag', value: 'React' }, pageIndex: 2, mobilePageIndex: 1 }));
s = topStore.getState();
console.assert(s.filter.value === 'React' && s.pageIndex === 2 && s.mobilePageIndex === 1, 'Restore state failed');

// 6. 初期状態リセット (ヘッダーロゴクリック時)
topStore.dispatch(actions.resetState());
s = topStore.getState();
console.assert(s.filter.type === 'all' && s.pageIndex === 0 && s.mobilePageIndex === 0, 'Reset state failed');

// 7. filterArticles 純粋関数のテスト
const dummyArticles = [
    { title: 'Docker入門', tags: ['Docker', 'DevOps'] },
    { title: 'Python自動化', tags: ['Python'] },
    { title: 'React実践', tags: ['Frontend', 'React'] }
];
console.assert(filterArticles(dummyArticles, { type: 'all' }).length === 3, 'Filter all failed');
console.assert(filterArticles(dummyArticles, { type: 'tag', value: 'Docker' }).length === 1, 'Filter tag failed');
console.assert(filterArticles(dummyArticles, { type: 'search', value: '動化' }).length === 1, 'Filter search keyword failed');
console.assert(filterArticles(dummyArticles, { type: 'search', value: 'notfound' }).length === 0, 'Filter search empty failed');

console.log('test_top_store.js passed successfully!');
`;

const context = {
    console,
    window: {
        location: { search: '', pathname: '/' },
        history: { pushState() {}, replaceState() {} },
        addEventListener() {},
        scrollTo() {},
        matchMedia: () => ({ matches: false, addEventListener: () => {} })
    },
    document: {
        createElement: () => ({ appendChild() {}, classList: { add() {}, remove() {}, contains: () => false, toggle() {} }, style: {}, dataset: {}, setAttribute() {}, getAttribute: () => null, querySelectorAll: () => [], querySelector: () => null, addEventListener() {}, removeEventListener() {} }),
        head: { appendChild() {} },
        body: { appendChild() {} },
        title: '',
        getElementById: () => null,
        querySelectorAll: () => [],
        querySelector: () => null,
        addEventListener() {}
    },
    DOMPurify: { sanitize: s => s, addHook: () => {} },
    MonoMD: { getMonoMDCSS: () => '' },
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
};

vm.createContext(context);
vm.runInContext(scriptContent + '\n' + testCode, context);
