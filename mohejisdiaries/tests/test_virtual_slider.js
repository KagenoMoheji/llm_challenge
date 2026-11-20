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
// 実際のブラウザDOMと同様に children (Element子ノード) を正しく追跡するモックを作成
function createMockPageDiv() {
    let _html = '';
    return {
        get innerHTML() { return _html; },
        set innerHTML(v) {
            _html = v;
        },
        get children() {
            // HTML内のタグ（Element）の数を検出するシミュレーション
            const elementMatches = _html.match(/<[a-z0-9-]+(?:\s+[^>]*?)?>/gi) || [];
            return elementMatches;
        }
    };
}

const mockPages = [];
for (let p = 0; p < totalPages; p++) {
    const pageDiv = createMockPageDiv();
    if (p <= SLIDER_VIRTUAL_WINDOW) {
        pageDiv.innerHTML = generateDesktopPageHtml(p, totalPages, dummyArticles, ARTICLES_PER_PAGE);
    }
    mockPages.push(pageDiv);
}
const mockTrack = { children: mockPages };

// 初期状態チェック: 0と1のみ実DOMが存在し、2〜7は空
console.assert(mockPages[0].children.length > 0, 'Page 0 has DOM initially');
console.assert(mockPages[1].children.length > 0, 'Page 1 has DOM initially');
console.assert(mockPages[2].children.length === 0, 'Page 2 is empty initially');
console.assert(mockPages[7].children.length === 0, 'Page 7 is empty initially');

// テストケースA: ページ0から最後のページ(Page 7)へ直接ジャンプ移動 (slider-dotでの一発ジャンプ)
const lastPageIndex = totalPages - 1; // 7
updateDesktopVirtualWindow(mockTrack, lastPageIndex, totalPages, dummyArticles, ARTICLES_PER_PAGE);
console.assert(mockPages[lastPageIndex].children.length > 0, 'Last page must be rendered after direct jump from page 0');
console.assert(mockPages[lastPageIndex].innerHTML.includes('最　古'), 'Last page must contain oldest tile');
console.assert(mockPages[lastPageIndex - 1].children.length > 0, 'Page before last must be rendered within window');
console.assert(mockPages[0].children.length === 0, 'Page 0 must be pruned when at last page');

// テストケースB: 最後のページ(7)から1つ前(6)に戻る
updateDesktopVirtualWindow(mockTrack, lastPageIndex - 1, totalPages, dummyArticles, ARTICLES_PER_PAGE);
console.assert(mockPages[lastPageIndex - 1].children.length > 0, 'Page 6 must have tiles');
console.assert(mockPages[lastPageIndex].children.length > 0, 'Page 7 should stay loaded within window');

// テストケースC: 再び最後のページ(7)へ進む
updateDesktopVirtualWindow(mockTrack, lastPageIndex, totalPages, dummyArticles, ARTICLES_PER_PAGE);
console.assert(mockPages[lastPageIndex].children.length > 0, 'Last page must still be rendered when returning to it');
console.assert(mockPages[lastPageIndex].innerHTML.includes('最　古'), 'Last page must still contain oldest tile');

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

// 6. 上下両方のページネーションドットコンテナのHTML検証
console.log('6. Verifying dual pagination containers (top & bottom) in HTML...');
console.assert(html.includes('id="slider-pagination-desktop"'), 'Top desktop pagination exists');
console.assert(html.includes('id="slider-pagination-desktop-bottom"'), 'Bottom desktop pagination exists');
console.assert(html.includes('id="slider-pagination-mobile"'), 'Top mobile pagination exists');
console.assert(html.includes('id="slider-pagination-mobile-bottom"'), 'Bottom mobile pagination exists');
console.log('Dual pagination containers HTML check passed.');
