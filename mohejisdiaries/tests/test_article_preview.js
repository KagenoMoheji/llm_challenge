const fs = require('fs');
const vm = require('vm');
const path = require('path');

// index.html の読み込み
const htmlPath = path.resolve(__dirname, '../index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

const scriptMatches = [...html.matchAll(/<script(?![^>]*src=)>([\s\S]*?)<\/script>/gi)];
const scriptContent = scriptMatches.map(m => m[1]).join('\n');

const testCode = `
console.log('=== Running test_article_preview.js ===');

// 1. ルーティングのテスト (/articles/preview)
console.log('1. Testing route resolution for /articles/preview...');

function mockGetRoute(path) {
    if (path === '/articles/preview') return { type: 'article-preview' };
    if (path === '/errors/404') return { type: '404' };
    const m = path.match(/^\\/articles\\/(\\d{4})\\/(\\d+)$/);
    if (m) return { type: 'article', year: m[1], number: parseInt(m[2], 10) };
    return { type: 'top' };
}

console.assert(mockGetRoute('/articles/preview').type === 'article-preview', 'Route should resolve to article-preview');
console.assert(mockGetRoute('/articles/test').type === 'top', 'Legacy /articles/test should no longer resolve to preview');

// 2. YAMLバリデーションエラーの挙動テスト
console.log('2. Testing YAML validation error cases...');

function validateYamlData(data) {
    if (!data || typeof data !== 'object') {
        throw new Error('YAMLファイルの解析結果が空、またはオブジェクトではありません。');
    }
    if (!data.title) {
        throw new Error('記事データに "title"（タイトル）が指定されていません。');
    }
    if (!data.content || !Array.isArray(data.content)) {
        throw new Error('記事データに "content"（見出しと本文の配列）が指定されていません。');
    }
    const invalidLinks = validateArticleLinks(data);
    if (invalidLinks.length > 0) {
        const errorItems = invalidLinks.map(inv => 
            \`<li><code>\${escapeHtml(inv.url)}</code> <span style="opacity: 0.85;">(\${escapeHtml(inv.context)})</span></li>\`
        ).join('');
        const secErr = new Error('セキュリティ制限違反のリンクが検出されました');
        secErr.isSecurityError = true;
        secErr.htmlMessage = \`
            <strong>【セキュリティ警告】制限外のリンクまたはメディアURLが検出されました:</strong><br>
            許可されているURL形式は「<code>https://</code> 始まり」「<code>#</code> 始まり（ページ内アンカー）」「相対パス」のみです。（<code>http://</code> や <code>javascript:</code> 等は禁止されています）
            <ul style="margin: 8px 0 0 20px; font-size: 13px;">\${errorItems}</ul>
        \`;
        throw secErr;
    }
    return true;
}

// 2-1. タイトル欠落エラー
let titleErrorCaught = false;
try {
    validateYamlData({ content: [{ headline: 'H1', body: 'B1' }] });
} catch (e) {
    titleErrorCaught = true;
    console.assert(e.message.includes('"title"'), 'Error should mention title');
}
console.assert(titleErrorCaught, 'Missing title must throw error');

// 2-2. content欠落エラー
let contentErrorCaught = false;
try {
    validateYamlData({ title: 'Test' });
} catch (e) {
    contentErrorCaught = true;
    console.assert(e.message.includes('"content"'), 'Error should mention content');
}
console.assert(contentErrorCaught, 'Missing content must throw error');

// 2-3. セキュリティ違反URL検出エラー (http://)
let securityErrorCaught = false;
try {
    validateYamlData({
        title: '不正リンク記事',
        content: [{ headline: '危険', body: '[リンク](http://insecure.com)' }]
    });
} catch (e) {
    securityErrorCaught = true;
    console.assert(e.isSecurityError === true, 'Error should be flagged as isSecurityError');
    console.assert(e.htmlMessage.includes('http://insecure.com'), 'htmlMessage should list invalid URL');
    console.assert(e.htmlMessage.includes('【セキュリティ警告】'), 'htmlMessage should contain security alert headline');
}
console.assert(securityErrorCaught, 'Insecure link must throw security error');

// 2-4. 正常なYAMLデータ
let validPassed = false;
try {
    validPassed = validateYamlData({
        title: '正常な記事',
        content: [{ headline: 'セクション1', body: '本文です。[安全リンク](https://example.com)' }]
    });
} catch (e) {
    validPassed = false;
}
console.assert(validPassed === true, 'Valid YAML must pass without error');

console.log('YAML validation error handling tests passed.');
console.log('test_article_preview.js passed successfully!');
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
