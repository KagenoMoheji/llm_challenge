const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

console.log('=== Running test_profile_section.js ===');

const htmlPath = path.resolve(__dirname, '../index.html');
const htmlContent = fs.readFileSync(htmlPath, 'utf8');

// 1. CSSスタイルの存在とプロパティ検証
console.log('1. Verifying Profile Section CSS styles in index.html...');
assert(htmlContent.includes('.profile-section'), 'CSS must define .profile-section');
assert(htmlContent.includes('.profile-card'), 'CSS must define .profile-card');
assert(htmlContent.includes('.profile-avatar'), 'CSS must define .profile-avatar');
assert(htmlContent.includes('.profile-social-link'), 'CSS must define .profile-social-link');
assert(htmlContent.includes('.profile-thread-link'), 'CSS must define .profile-thread-link');

// 2. renderProfileSectionHtml 関数の抽出と実行検証
console.log('2. Testing renderProfileSectionHtml function execution...');
const scriptMatch = htmlContent.match(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/i);
assert(scriptMatch, 'Inline script block not found');
const scriptCode = scriptMatch[1];

// 最小限のブラウザAPIモック
const sandbox = {
    document: {
        createElement: (tag) => ({
            tag,
            innerHTML: '',
            style: {},
            textContent: ''
        }),
        head: { appendChild: () => {} },
        body: { appendChild: () => {} },
        title: '',
        getElementById: () => null,
        querySelectorAll: () => [],
        querySelector: () => null,
        addEventListener: () => {}
    },
    window: {
        location: { pathname: '/', search: '' },
        history: { pushState: () => {}, replaceState: () => {} },
        addEventListener: () => {},
        scrollTo: () => {}
    },
    MonoMD: {
        getMonoMDCSS: () => '',
        renderMarkdown: async () => ({ html: '' })
    },
    DOMPurify: { sanitize: s => s },
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
    console
};
vm.createContext(sandbox);

// 必要な関数をスクリプトから取り出して検証
const funcCode = `
${scriptCode}
globalThis.renderProfileSectionHtml = renderProfileSectionHtml;
`;
vm.runInContext(funcCode, sandbox);

const profileHtml = sandbox.renderProfileSectionHtml();
assert(typeof profileHtml === 'string', 'renderProfileSectionHtml must return a string');

// 3. プロフィール要素とリンクの検証
console.log('3. Verifying profile elements, images, and links in rendered HTML...');
assert(profileHtml.includes('src="media/profile.svg"'), 'Profile image must point to media/profile.svg');
assert(profileHtml.includes('class="profile-avatar"'), 'Profile avatar must have profile-avatar class');
assert(profileHtml.includes('https://github.com/KagenoMoheji'), 'GitHub link must be present');
assert(profileHtml.includes('https://x.com/KagenoMoheji'), 'X(Twitter) link must be present');
assert(profileHtml.includes('https://x.com/KagenoMoheji/status/1377470980897955841?a=WQ5vfv1wsl0KNUPOiBM&s=20'), 'Food thread link must be present');
assert(profileHtml.includes('食べ歩きスレッド'), 'Text "食べ歩きスレッド" must be present');
assert(profileHtml.includes('target="_blank"'), 'External links must have target="_blank"');
assert(profileHtml.includes('rel="noopener noreferrer"'), 'External links must have rel="noopener noreferrer"');

// 4. 実ファイルの存在確認
console.log('4. Verifying existence of media/profile.svg on filesystem...');
const profileSvgPath = path.resolve(__dirname, '../media/profile.svg');
assert(fs.existsSync(profileSvgPath), 'media/profile.svg must exist');

console.log('test_profile_section.js passed successfully!');
