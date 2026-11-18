const fs = require('fs');
const path = require('path');

const htmlPath = path.resolve(__dirname, '../index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const styleMatches = [...html.matchAll(/<style>([\s\S]*?)<\/style>/gi)];

console.log('Found', styleMatches.length, 'style blocks');
let hasError = false;

styleMatches.forEach((match, i) => {
    const css = match[1];
    const openBraces = (css.match(/\{/g) || []).length;
    const closeBraces = (css.match(/\}/g) || []).length;
    console.log(`Style block ${i + 1}: Open braces: ${openBraces}, Close braces: ${closeBraces}`);
    if (openBraces !== closeBraces) {
        console.error(`Mismatch in CSS braces in style block ${i + 1}!`);
        hasError = true;
    }
});

if (hasError) {
    process.exit(1);
}
console.log('CSS syntax validation passed!');
