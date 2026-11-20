const { execSync } = require('child_process');
const path = require('path');

const tests = [
    { name: 'CSS Syntax Validation', script: 'tests/validate_css.js' },
    { name: 'JavaScript Syntax Validation', script: 'tests/validate_js.js' },
    { name: 'Redux Store Unit Tests', script: 'tests/test_top_store.js' },
    { name: 'Virtual Slider Tests', script: 'tests/test_virtual_slider.js' },
    { name: 'Article Tags & Navigation Tests', script: 'tests/test_article_tags.js' },
    { name: 'Link & URL Validation Tests', script: 'tests/test_link_validation.js' },
    { name: 'DOMPurify & SRI Security Tests', script: 'tests/test_dompurify_sanitizer.js' },
    { name: 'CDN SRI Hash Verification Tests', script: 'tests/test_sri_hash.js' },
    { name: 'Article Preview & YAML Parsing Tests', script: 'tests/test_article_preview.js' }
];

console.log('====================================================');
console.log('Running Mohejis Diaries Frontend Test Suite');
console.log('====================================================\n');

let failed = false;

for (const test of tests) {
    console.log(`>>> [RUN] ${test.name} (${test.script})`);
    try {
        const output = execSync(`node ${test.script}`, {
            cwd: path.resolve(__dirname, '..'),
            encoding: 'utf8',
            stdio: 'pipe'
        });
        console.log(output.trim());
        console.log(`>>> [PASS] ${test.name}\n`);
    } catch (err) {
        console.error(`>>> [FAIL] ${test.name}`);
        if (err.stdout) console.log(err.stdout.toString());
        if (err.stderr) console.error(err.stderr.toString());
        failed = true;
        break;
    }
}

console.log('====================================================');
if (failed) {
    console.error('Test Suite FAILED!');
    process.exit(1);
} else {
    console.log(`All ${tests.length} test suites PASSED successfully!`);
    console.log('====================================================');
}
