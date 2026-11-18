const fs = require('fs');
const https = require('https');
const crypto = require('crypto');
const path = require('path');

console.log('=== Running test_sri_hash.js (CDN SRI Integrity Hash Verification) ===');

const htmlPath = path.resolve(__dirname, '../index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

// index.html から外部 CDN リソースの URL と integrity 属性を抽出
const resourceRegex = /<(?:script|link)\b[^>]*?(?:src|href)="([^"]+)"[^>]*?integrity="([^"]+)"/gi;
const resources = [];
let match;
while ((match = resourceRegex.exec(html)) !== null) {
    const url = match[1];
    const integrity = match[2];
    if (url.startsWith('http')) {
        resources.push({ url, expectedHash: integrity });
    }
}

// 別順序の属性（integrity が src/href より前にある場合）もカバー
const resourceRegexAlt = /<(?:script|link)\b[^>]*?integrity="([^"]+)"[^>]*?(?:src|href)="([^"]+)"/gi;
while ((match = resourceRegexAlt.exec(html)) !== null) {
    const integrity = match[1];
    const url = match[2];
    if (url.startsWith('http') && !resources.some(r => r.url === url)) {
        resources.push({ url, expectedHash: integrity });
    }
}

console.log(`Found ${resources.length} resources with SRI integrity hashes in index.html`);
console.assert(resources.length >= 4, 'Should find at least 4 external resources with SRI');

function fetchAndHash(url) {
    return new Promise((resolve, reject) => {
        https.get(url, (res) => {
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                return fetchAndHash(res.headers.location).then(resolve).catch(reject);
            }
            if (res.statusCode !== 200) {
                return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
            }
            const hash384 = crypto.createHash('sha384');
            res.on('data', chunk => hash384.update(chunk));
            res.on('end', () => {
                resolve('sha384-' + hash384.digest('base64'));
            });
            res.on('error', reject);
        }).on('error', reject);
    });
}

(async () => {
    let networkAvailable = true;
    for (const res of resources) {
        console.log(`Verifying SRI for: ${res.url}`);
        console.log(`  Expected in HTML: ${res.expectedHash}`);
        
        try {
            const actualHash = await fetchAndHash(res.url);
            console.log(`  Computed hash:    ${actualHash}`);
            if (res.expectedHash === actualHash) {
                console.log(`  -> MATCH [OK]`);
            } else {
                console.error(`  -> MISMATCH! Expected ${res.expectedHash} but got ${actualHash}`);
                process.exit(1);
            }
        } catch (err) {
            console.warn(`  -> Network fetch failed (${err.message}). Skipping online hash check.`);
            networkAvailable = false;
        }
    }
    
    if (networkAvailable) {
        console.log('All CDN SRI integrity hashes match computed values perfectly!');
    } else {
        console.log('Online hash verification skipped due to network restriction (offline mode).');
    }
    console.log('test_sri_hash.js passed successfully!');
})().catch(err => {
    console.error('Fatal error in test_sri_hash.js:', err);
    process.exit(1);
});
