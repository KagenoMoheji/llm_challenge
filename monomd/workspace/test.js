const { renderMarkdown, parseInline, parseList, escapeHtml, getMonoMDCSS } = require('./index.js');

async function runTests() {
    console.log('🧪 MonoMD Test Suite\n');
    let passed = 0;
    let failed = 0;

    // Test 1: Headings
    console.log('Test 1: Headings');
    try {
        const md = '# H1\n## H2\n### H3';
        const result = await renderMarkdown(md);
        if (result.html.includes('<h1>') && result.html.includes('<h2>') && result.html.includes('<h3>')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('HTML does not contain expected headings');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 2: Text Formatting
    console.log('Test 2: Text Formatting');
    try {
        const md = 'This is **bold**, __underline__, ~~strikethrough~~, and `code`.';
        const result = await renderMarkdown(md);
        if (result.html.includes('<b>bold</b>') && 
            result.html.includes('<u>underline</u>') && 
            result.html.includes('<s>strikethrough</s>') && 
            result.html.includes('<code>code</code>')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Text formatting not correctly applied');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 3: Unordered Lists
    console.log('Test 3: Unordered Lists');
    try {
        const md = `- Item 1
- Item 2
  - Nested item
- Item 3`;
        const result = await renderMarkdown(md);
        if (result.html.includes('<ul>') && result.html.includes('<li>')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('List not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 4: Ordered Lists
    console.log('Test 4: Ordered Lists');
    try {
        const md = `1. First
2. Second
3. Third`;
        const result = await renderMarkdown(md);
        if (result.html.includes('<ol>') && result.html.includes('<li>')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Ordered list not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 5: Checklists
    console.log('Test 5: Checklists');
    try {
        const md = `- [ ] Unchecked
- [x] Checked`;
        const result = await renderMarkdown(md);
        if (result.html.includes('type="checkbox"') && result.html.includes('checked')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Checklist not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 6: Links
    console.log('Test 6: Links');
    try {
        const md = 'Check out [Google](https://google.com)';
        const result = await renderMarkdown(md);
        if (result.html.includes('<a href="https://google.com"')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Link not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 7: Internal Links
    console.log('Test 7: Internal Links');
    try {
        const md = '!!Article Title!!(/articles/2019/1)';
        const result = await renderMarkdown(md);
        if (result.html.includes('class="internal-link"') && result.html.includes('data-path=')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Internal link not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 8: Code Block
    console.log('Test 8: Code Block');
    try {
        const md = '```javascript\nconst x = 10;\nconsole.log(x);\n```';
        const result = await renderMarkdown(md);
        if (result.html.includes('<pre><code>')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Code block not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 9: Code Block with Output
    console.log('Test 9: Code Block with Output');
    try {
        const md = '```python\nprint("Hello")\n:::output\nHello\n:::\n```';
        const result = await renderMarkdown(md);
        if (result.html.includes('code-block-container') && 
            result.html.includes('code-program') && 
            result.html.includes('code-output')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Code block with output not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 10: Table
    console.log('Test 10: Table');
    try {
        const md = `| Name | Age |
|------|:---:|
| Alice | 25 |
| Bob | 30 |`;
        const result = await renderMarkdown(md);
        if (result.html.includes('<table>') && result.html.includes('Name') && result.html.includes('Alice')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Table not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 11: Table with Caption
    console.log('Test 11: Table with Caption');
    try {
        const md = `| Name | Age |[Employee Data]
|------|-----|
| Alice | 25 |`;
        const result = await renderMarkdown(md);
        if (result.html.includes('<caption>Employee Data</caption>')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Table caption not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 12: Blockquote
    console.log('Test 12: Blockquote');
    try {
        const md = '> This is a quote';
        const result = await renderMarkdown(md);
        if (result.html.includes('<blockquote>')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Blockquote not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 13: Nested Blockquotes
    console.log('Test 13: Nested Blockquotes');
    try {
        const md = '> Level 1\n> > Level 2';
        const result = await renderMarkdown(md);
        if (result.html.includes('<blockquote>') && result.html.match(/<blockquote>/g).length >= 2) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Nested blockquotes not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 14: Info Block
    console.log('Test 14: Info Block');
    try {
        const md = ':::info\nThis is information\n:::';
        const result = await renderMarkdown(md);
        if (result.html.includes('info-block') && result.html.includes('info-type-info')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Info block not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 15: Warn Block
    console.log('Test 15: Warn Block');
    try {
        const md = ':::warn\nThis is a warning\n:::';
        const result = await renderMarkdown(md);
        if (result.html.includes('info-block') && result.html.includes('info-type-warn')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Warn block not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 16: Alert Block
    console.log('Test 16: Alert Block');
    try {
        const md = ':::alert\nThis is an alert\n:::';
        const result = await renderMarkdown(md);
        if (result.html.includes('info-block') && result.html.includes('info-type-alert')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Alert block not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 17: Image
    console.log('Test 17: Image');
    try {
        const md = '![Alt text](https://example.com/image.jpg)';
        const result = await renderMarkdown(md);
        if (result.html.includes('<figure class="article-image">') && 
            result.html.includes('<img src=') && 
            result.html.includes('<figcaption>')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Image not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 18: HTML Escape
    console.log('Test 18: HTML Escape');
    try {
        const unsafe = '<script>alert("XSS")</script>';
        const escaped = escapeHtml(unsafe);
        if (escaped.includes('&lt;') && escaped.includes('&gt;')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('HTML not escaped correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 19: CSS Generation
    console.log('Test 19: CSS Generation');
    try {
        const css = getMonoMDCSS();
        if (css.includes('.monomd-body') && css.includes('--accent')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('CSS not generated correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Test 20: Escaped Characters
    console.log('Test 20: Escaped Characters');
    try {
        const md = '\\*Not bold\\* and \\[Not a link\\]';
        const result = await renderMarkdown(md);
        if (result.html.includes('*Not bold*') && result.html.includes('[Not a link]')) {
            console.log('✅ Pass\n');
            passed++;
        } else {
            throw new Error('Escaped characters not handled correctly');
        }
    } catch (error) {
        console.log(`❌ Fail: ${error.message}\n`);
        failed++;
    }

    // Summary
    console.log('='.repeat(50));
    console.log(`Tests Passed: ${passed}/${passed + failed}`);
    console.log(`Tests Failed: ${failed}/${passed + failed}`);
    console.log('='.repeat(50));
    
    if (failed === 0) {
        console.log('\n🎉 All tests completed successfully!');
    } else {
        console.log(`\n⚠️  ${failed} test(s) failed.`);
    }
}

// Run tests
runTests().catch(console.error);