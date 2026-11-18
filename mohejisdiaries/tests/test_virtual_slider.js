const fs = require('fs');
const vm = require('vm');
const path = require('path');

// index.html の読み込み
const htmlPath = path.resolve(__dirname, '../index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

const scriptMatches = [...html.matchAll(/<script(?![^>]*src=)>([\s\S]*?)<\/script>/gi)];
const scriptContent = scriptMatches.map(m => m[1]).join('\n');

const testCode = `
console.log('=== Running test_virtual_slider.js ===');

// 1. 定数・仮想ウィンドウ設定の検証
console.assert(typeof SLIDER_VIRTUAL_WINDOW === 'number', 'SLIDER_VIRTUAL_WINDOW should be defined');
console.assert(SLIDER_VIRTUAL_WINDOW === 1, 'SLIDER_VIRTUAL_WINDOW should be 1 (current ± 1 page)');

// 2. ダミー記事データの準備 (50記事)
const dummyArticles = Array.from({ length: 50 }, (_, i) => ({
    id: '202300' + (i + 1),
    createDate: '2023-01-01',
    title: '記事タイトル ' + (i + 1),
    snippet: 'スニペット ' + (i + 1),
    thumbnail: '',
    tags: ['Tag' + (i % 3)]
}));

// 3. PC版スライダーHTML生成 (generateDesktopPageHtml)
const ARTICLES_PER_PAGE = 7;
const totalPages = Math.ceil(dummyArticles.length / ARTICLES_PER_PAGE); // 8ページ

// 3-1. 0ページ目（先頭）: 「最　新」タイル、「過　去」タイルが含まれること
const p0Html = generateDesktopPageHtml(0, totalPages, dummyArticles, ARTICLES_PER_PAGE);
console.assert(p0Html.includes('記事タイトル 1'), 'Page 0 should contain article 1');
console.assert(p0Html.includes('記事タイトル 7'), 'Page 0 should contain article 7');
console.assert(p0Html.includes('nav-tile-latest'), 'Page 0 should contain latest nav-tile');
console.assert(p0Html.includes('最　新'), 'Page 0 should show "最　新"');
console.assert(p0Html.includes('nav-tile-next'), 'Page 0 should contain next nav-tile');
console.assert(p0Html.includes('過　去'), 'Page 0 should show "過　去"');

// 3-2. 1ページ目（中間）: 「最　近」タイル、「過　去」タイルが含まれること
const p1Html = generateDesktopPageHtml(1, totalPages, dummyArticles, ARTICLES_PER_PAGE);
console.assert(p1Html.includes('記事タイトル 8'), 'Page 1 should contain article 8');
console.assert(p1Html.includes('nav-tile-prev'), 'Page 1 should contain prev nav-tile');
console.assert(p1Html.includes('最　近'), 'Page 1 should show "最　近"');
console.assert(p1Html.includes('nav-tile-next'), 'Page 1 should contain next nav-tile');

// 3-3. 最終ページ（Page 7: 記事 50）: 「最　古」タイルが含まれ、次へリンクがないこと
const pLastHtml = generateDesktopPageHtml(totalPages - 1, totalPages, dummyArticles, ARTICLES_PER_PAGE);
console.assert(pLastHtml.includes('記事タイトル 50'), 'Last page should contain article 50');
console.assert(pLastHtml.includes('nav-tile-oldest'), 'Last page should contain oldest nav-tile');
console.assert(pLastHtml.includes('最　古'), 'Last page should show "最　古"');
console.assert(!pLastHtml.includes('nav-tile-next'), 'Last page must not contain next nav-tile');

// 4. スマホ版スライダーHTML生成 (generateMobilePageHtml: 10記事/ページ)
const MOBILE_PER_PAGE = 10;
const mobileTotalPages = Math.ceil(dummyArticles.length / MOBILE_PER_PAGE); // 5ページ
const m0Html = generateMobilePageHtml(0, mobileTotalPages, dummyArticles, MOBILE_PER_PAGE);
console.assert(m0Html.includes('記事タイトル 1'), 'Mobile page 0 should contain article 1');
console.assert(m0Html.includes('記事タイトル 10'), 'Mobile page 0 should contain article 10');
console.assert(!m0Html.includes('記事タイトル 11'), 'Mobile page 0 must not contain article 11');

// 5. 動的DOMウィンドウ更新 (updateDesktopVirtualWindow)
const mockPages = [];
for (let p = 0; p < totalPages; p++) {
    const pageDiv = {
        _html: '',
        get innerHTML() { return this._html; },
        set innerHTML(v) { this._html = v; },
        hasChildNodes() { return this._html.trim().length > 0; }
    };
    if (p <= SLIDER_VIRTUAL_WINDOW) {
        pageDiv.innerHTML = generateDesktopPageHtml(p, totalPages, dummyArticles, ARTICLES_PER_PAGE);
    }
    mockPages.push(pageDiv);
}
const mockTrack = { children: mockPages };

// 初期状態チェック: 0と1のみ実DOMが存在し、2〜7は空
console.assert(mockPages[0].hasChildNodes() === true, 'Page 0 has DOM initially');
console.assert(mockPages[1].hasChildNodes() === true, 'Page 1 has DOM initially');
console.assert(mockPages[2].hasChildNodes() === false, 'Page 2 is empty initially');
console.assert(mockPages[7].hasChildNodes() === false, 'Page 7 is empty initially');

// ページ3へジャンプ移動 (centerPage = 3)
// 仮想ウィンドウ範囲: |p - 3| <= 1 (2, 3, 4)
// 0, 1 は範囲外なので破棄されること
// 2, 3, 4 は動的に実DOMが生成されること
// 5, 6, 7 は空のままであること
updateDesktopVirtualWindow(mockTrack, 3, totalPages, dummyArticles, ARTICLES_PER_PAGE);
console.assert(mockPages[0].hasChildNodes() === false, 'Page 0 was pruned');
console.assert(mockPages[1].hasChildNodes() === false, 'Page 1 was pruned');
console.assert(mockPages[2].hasChildNodes() === true, 'Page 2 was dynamically created');
console.assert(mockPages[3].hasChildNodes() === true, 'Page 3 was dynamically created');
console.assert(mockPages[4].hasChildNodes() === true, 'Page 4 was dynamically created');
console.assert(mockPages[5].hasChildNodes() === false, 'Page 5 remains empty');

console.log('test_virtual_slider.js passed successfully!');
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
        createElement: () => {
            let content = '';
            return {
                appendChild() {},
                get textContent() { return content; },
                set textContent(val) { content = String(val); },
                get innerHTML() { return content; },
                set innerHTML(val) { content = String(val); },
                classList: { add() {}, remove() {}, contains: () => false, toggle() {} },
                style: {},
                dataset: {},
                setAttribute() {},
                getAttribute: () => null,
                querySelectorAll: () => [],
                querySelector: () => null,
                addEventListener() {},
                removeEventListener() {}
            };
        },
        head: { appendChild() {} },
        body: { appendChild() {} },
        title: '',
        getElementById: () => null,
        querySelectorAll: () => [],
        querySelector: () => null,
        addEventListener: () => {}
    },
    DOMPurify: { sanitize: s => s, addHook: () => {} },
    MonoMD: { getMonoMDCSS: () => '' },
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
};

vm.createContext(context);
vm.runInContext(scriptContent + '\n' + testCode, context);
