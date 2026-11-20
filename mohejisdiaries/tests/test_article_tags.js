const fs = require('fs');
const vm = require('vm');
const path = require('path');

// index.html の読み込み
const htmlPath = path.resolve(__dirname, '../index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

const scriptMatches = [...html.matchAll(/<script(?![^>]*src=)>([\s\S]*?)<\/script>/gi)];
const scriptContent = scriptMatches.map(m => m[1]).join('\n');

const testCode = `
console.log('=== Running test_article_tags.js ===');

(async () => {
    // 1. 初期状態
    let s = topStore.getState();
    console.assert(s.filter.type === 'all' && s.pageIndex === 0 && s.mobilePageIndex === 0, 'Initial state failed');

    // 2. buildArticleHtml で記事詳細下部のタグが .sidebar-tag-item .article-tag-item として正しくレンダリングされるか
    const sampleArticle = {
        title: 'タグ表示テスト記事',
        date: '2023-01-01',
        content: [{ headline: '見出し1', body: '本文1' }],
        tags: ['Docker', 'TypeScript', 'Node.js']
    };
    const articleHtml = await buildArticleHtml(sampleArticle);
    
    // タグコンテナとタグ要素のクラス・属性の検証
    console.assert(articleHtml.includes('<div class="tags-container">'), 'tags-container div missing');
    console.assert(articleHtml.includes('class="sidebar-tag-item article-tag-item" data-tag="Docker"'), 'Docker tag rendering failed');
    console.assert(articleHtml.includes('class="sidebar-tag-item article-tag-item" data-tag="TypeScript"'), 'TypeScript tag rendering failed');
    console.assert(articleHtml.includes('class="sidebar-tag-item article-tag-item" data-tag="Node.js"'), 'Node.js tag rendering failed');
    console.log('buildArticleHtml tag elements rendering OK');

    // 3. navigateToTag のテスト (記事下部タグクリック時に呼ばれ、トップページをそのタグで絞り込む)
    await navigateToTag('Docker');
    s = topStore.getState();
    console.assert(s.filter.type === 'tag' && s.filter.value === 'Docker', 'navigateToTag did not set tag filter in topStore');
    console.assert(s.pageIndex === 0 && s.mobilePageIndex === 0, 'navigateToTag did not reset page index to 0');
    console.log('navigateToTag state update & page reset OK');

    // 4. 再度初期化 (トップページ全件表示に戻す)
    topStore.dispatch(actions.resetState());
    s = topStore.getState();
    console.assert(s.filter.type === 'all' && s.pageIndex === 0, 'Reset failed');

    console.log('test_article_tags.js passed successfully!');
})().catch(e => {
    console.error('Test execution failed:', e);
    process.exit(1);
});
`;

let renderedTop = false;
const context = {
    console,
    process,
    window: {
        location: { search: '', pathname: '/articles/2023/1' },
        history: { pushState(state, title, url){ this.state = state; this.url = url; }, replaceState(){} },
        addEventListener(){},
        scrollTo(){}
    },
    document: {
        createElement: (tag) => {
            let _content = '';
            return {
                set textContent(v) { _content = v; },
                get textContent() { return _content; },
                get innerHTML() { return _content; },
                appendChild(){}
            };
        },
        head: { appendChild(){} },
        title: '',
        getElementById: (id) => {
            return {
                innerHTML: '',
                value: '',
                style: {},
                querySelectorAll: () => [],
                addEventListener: () => {}
            };
        },
        querySelectorAll: () => [],
        querySelector: () => null
    },
    DOMPurify: {
        sanitize: s => s,
        addHook: () => {}
    },
    MonoMD: {
        getMonoMDCSS: () => '',
        renderMarkdown: async (md) => ({ html: '<div class="monomd-body">' + md + '</div>' })
    },
    fetch: () => Promise.resolve({
        ok: true,
        json: () => Promise.resolve([
            { id: '2023001', title: '記事1', tags: ['Docker'] }
        ])
    })
};

vm.createContext(context);
vm.runInContext(scriptContent + '\n' + testCode, context);
