const fs = require('fs');
const path = require('path');

// index.html の読み込み
const htmlPath = path.resolve(__dirname, '../index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

console.log('=== Running test_dompurify_sanitizer.js ===');

// 1. SRI (Subresource Integrity) と crossorigin 属性の検証
console.log('1. Checking CDN Script & Link SRI attributes in index.html...');

const scriptTagRegex = /<script\b([^>]*)>/gi;
const linkTagRegex = /<link\b([^>]*)>/gi;

const externalResources = [];
let match;
while ((match = scriptTagRegex.exec(html)) !== null) {
    const attrs = match[1];
    const srcMatch = attrs.match(/src="([^"]+)"/i);
    if (srcMatch && srcMatch[1].startsWith('http')) {
        externalResources.push({ type: 'script', url: srcMatch[1], tag: match[0] });
    }
}
while ((match = linkTagRegex.exec(html)) !== null) {
    const attrs = match[1];
    const hrefMatch = attrs.match(/href="([^"]+)"/i);
    if (hrefMatch && hrefMatch[1].startsWith('http')) {
        externalResources.push({ type: 'link', url: hrefMatch[1], tag: match[0] });
    }
}

console.log(`Found ${externalResources.length} external CDN resources`);
console.assert(externalResources.length >= 4, 'Should have at least 4 external resources (js-yaml, dompurify, fontawesome, monomd)');

for (const res of externalResources) {
    const hasIntegrity = /integrity="sha(256|384|512)-[^"]+"/i.test(res.tag);
    const hasCrossOrigin = /crossorigin="anonymous"/i.test(res.tag);
    console.assert(hasIntegrity, `Resource ${res.url} is missing a valid integrity attribute!`);
    console.assert(hasCrossOrigin, `Resource ${res.url} is missing crossorigin="anonymous"!`);
}
console.log('All external resources have valid SRI and crossorigin attributes.');

// 2. DOMPURIFY_CONFIG 定義の検証
console.log('2. Verifying DOMPURIFY_CONFIG in index.html...');
console.assert(html.includes("ADD_TAGS: ['iframe', 'section']"), 'DOMPURIFY_CONFIG must allow iframe and section');
console.assert(html.includes("'src'"), 'DOMPURIFY_CONFIG must allow src attribute');
console.assert(html.includes("'data-path'"), 'DOMPURIFY_CONFIG must allow data-path attribute');
console.assert(html.includes("'data-tag'"), 'DOMPURIFY_CONFIG must allow data-tag attribute');
console.assert(html.includes("DATA_ATTR: true"), 'DOMPURIFY_CONFIG must allow data-* attributes');

// 3. CodePen iframe フォールバック正規化ロジックの検証
console.log('3. Testing CodePen fallback HTML iframe normalization...');

// 実際の CodePen 埋め込み形式（iframe 内に <a> タグなどのフォールバックが入っているもの）
const rawEmbedHtml = `
<iframe height="300" style="width: 100%;" scrolling="no" title="hello" src="https://codepen.io/KagenoMoheji/embed/dvZdyK" frameborder="no" loading="lazy">
  See the Pen <a href="https://codepen.io/KagenoMoheji/pen/dvZdyK">hello</a> by へのへのもへじ on CodePen.
</iframe>
<p class="codepen">See the Pen hello on CodePen.</p>
`;

// index.html の正規化正規表現
const normalized = rawEmbedHtml.replace(/<iframe\b([^>]*)>([\s\S]*?)<\/iframe>/gi, '<iframe$1></iframe>');

// フォールバック HTML が消去され、自己完結したクリーンな iframe になっていること
console.assert(normalized.includes('<iframe height="300" style="width: 100%;" scrolling="no" title="hello" src="https://codepen.io/KagenoMoheji/embed/dvZdyK" frameborder="no" loading="lazy"></iframe>'), 'iframe should be normalized to self-contained tag without inner fallback');
console.assert(!normalized.includes('See the Pen <a href="https://codepen.io/KagenoMoheji/pen/dvZdyK">'), 'Inner fallback <a> must be removed from inside iframe');
console.assert(normalized.includes('<p class="codepen">'), 'Outside elements must be preserved');

// 4. renderMarkdown 内での DOMPurify 呼び出し構造の検証
console.log('4. Verifying renderMarkdown sanitization pipeline...');
console.assert(html.includes('DOMPurify.sanitize(rawHtml, DOMPURIFY_CONFIG)'), 'renderMarkdown must pass rawHtml and DOMPURIFY_CONFIG to DOMPurify.sanitize');

console.log('test_dompurify_sanitizer.js passed successfully!');
