const fs = require('fs');
const path = require('path');

const htmlPath = path.resolve(__dirname, '../index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const scriptMatches = [...html.matchAll(/<script(?![^>]*src=)>([\s\S]*?)<\/script>/gi)];

console.log('Found', scriptMatches.length, 'inline scripts');
let hasError = false;

scriptMatches.forEach((match, i) => {
    try {
        new Function(match[1]);
        console.log(`Script block ${i + 1}: syntax OK`);
    } catch (e) {
        console.error(`Script block ${i + 1} syntax error:`, e.message);
        hasError = true;
    }
});

if (hasError) {
    process.exit(1);
}
console.log('JavaScript syntax validation passed!');
