const fs = require('fs');
const vm = require('vm');
const path = require('path');

// index.html の読み込み
const htmlPath = path.resolve(__dirname, '../index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

const scriptMatches = [...html.matchAll(/<script(?![^>]*src=)>([\s\S]*?)<\/script>/gi)];
const scriptContent = scriptMatches.map(m => m[1]).join('\n');

const testCode = `
console.log('=== Running test_link_validation.js ===');

// 1. isAllowedUrl 純粋関数のテスト
console.log('Testing isAllowedUrl...');

// 許可されるべきURL (https://, #, 相対パス)
console.assert(isAllowedUrl('https://example.com') === true, 'https:// should be allowed');
console.assert(isAllowedUrl('https://codepen.io/pen/xyz?param=1') === true, 'https:// with query should be allowed');
console.assert(isAllowedUrl('#section-1') === true, 'Anchor # should be allowed');
console.assert(isAllowedUrl('#') === true, 'Single # should be allowed');
console.assert(isAllowedUrl('media/image.png') === true, 'Relative media/ should be allowed');
console.assert(isAllowedUrl('./image.png') === true, 'Relative ./ should be allowed');
console.assert(isAllowedUrl('../media/image.png') === true, 'Relative ../ should be allowed');
console.assert(isAllowedUrl('/articles/2023/1') === true, 'Root relative / should be allowed');
console.assert(isAllowedUrl('?path=/articles/2023/1') === true, 'Query path ? should be allowed');

// 禁止されるべきURL (http://, javascript:, data:, file:, // 等)
console.assert(isAllowedUrl('http://example.com') === false, 'http:// must be rejected');
console.assert(isAllowedUrl('http://codepen.io') === false, 'http:// insecure codepen must be rejected');
console.assert(isAllowedUrl('javascript:alert(1)') === false, 'javascript: must be rejected');
console.assert(isAllowedUrl('javascript:void(0)') === false, 'javascript:void must be rejected');
console.assert(isAllowedUrl('data:text/html,<script>alert(1)</script>') === false, 'data: URI must be rejected');
console.assert(isAllowedUrl('file:///etc/passwd') === false, 'file: protocol must be rejected');
console.assert(isAllowedUrl('vbscript:msgbox(1)') === false, 'vbscript: protocol must be rejected');
console.assert(isAllowedUrl('//example.com/asset') === false, 'Protocol-relative // must be rejected');
console.assert(isAllowedUrl('') === false, 'Empty URL should be rejected');
console.assert(isAllowedUrl('   ') === false, 'Whitespace URL should be rejected');
console.assert(isAllowedUrl(null) === false, 'null should be rejected');

console.log('isAllowedUrl tests passed.');

// 2. validateArticleLinks のテスト (記事YAMLデータ全体のリンク抽出 & セキュリティチェック)
console.log('Testing validateArticleLinks...');

// 2-1. 安全な記事データ（全URLが許可対象）
const safeArticle = {
    title: '安全な記事',
    content: [
        {
            headline: 'セクション1',
            body: \`
                これは[公式サイト](https://secure.example.com)へのリンクです。
                画像は![写真](media/photo.png)です。
                内部リンクは!!次の記事!!(/articles/2023/2)です。
                ページ内アンカーは[目次へ](#toc)です。
                HTMLタグ: <iframe src="https://codepen.io/embed/abc"></iframe>
                HTMLリンク: <a href="https://example.org/test">リンク</a>
            \`
        }
    ]
};
const safeErrors = validateArticleLinks(safeArticle);
console.assert(safeErrors.length === 0, \`Safe article should have 0 errors, got \${safeErrors.length}\`);

// 2-2. 危険なURLを含む記事データ
const unsafeArticle = {
    title: '危険な記事',
    content: [
        {
            headline: '危険なセクション',
            body: \`
                [安全リンク](https://example.com)
                [危険な非暗号化リンク](http://insecure.example.com/api)
                ![危険な画像](http://insecure.example.com/pic.jpg)
                [XSS攻撃](javascript:alert(document.cookie))
                <a href="http://another-insecure.com">非暗号化HTML</a>
                <iframe src="http://codepen.io/embed/bad"></iframe>
                <img src="//protocol-relative.com/image.png">
            \`
        }
    ]
};
const unsafeErrors = validateArticleLinks(unsafeArticle);
console.assert(unsafeErrors.length === 6, \`Unsafe article should detect exactly 6 errors, got \${unsafeErrors.length}\`);

// 検出された不正URLの検証
const invalidUrls = unsafeErrors.map(e => e.url);
console.assert(invalidUrls.includes('http://insecure.example.com/api'), 'Should detect http:// in markdown link');
console.assert(invalidUrls.includes('http://insecure.example.com/pic.jpg'), 'Should detect http:// in markdown image');
console.assert(invalidUrls.includes('javascript:alert(document.cookie)'), 'Should detect javascript: in markdown link');
console.assert(invalidUrls.includes('http://another-insecure.com'), 'Should detect http:// in HTML href');
console.assert(invalidUrls.includes('http://codepen.io/embed/bad'), 'Should detect http:// in HTML iframe src');
console.assert(invalidUrls.includes('//protocol-relative.com/image.png'), 'Should detect // in HTML img src');

// コンテキスト情報の検証
console.assert(unsafeErrors[0].context.includes('危険なセクション'), 'Context should identify section title');

console.log('validateArticleLinks tests passed.');
console.log('test_link_validation.js passed successfully!');
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
        addEventListener: () => {}
    },
    DOMPurify: { sanitize: s => s, addHook: () => {} },
    MonoMD: { getMonoMDCSS: () => '' },
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
};

vm.createContext(context);
vm.runInContext(scriptContent + '\n' + testCode, context);
