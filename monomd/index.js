/**
 * MonoMD - A redundant-free Markdown parser where every symbol has its own unique role.
 * @version 1.0.0
 * @license MIT
 */

/**
 * HTMLエスケープ
 * @param {string} text - エスケープするテキスト
 * @returns {string} エスケープされたHTML
 */
function escapeHtml(text) {
    if (typeof document !== 'undefined') {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    } else {
        // Node.js環境用
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
}

/**
 * インライン要素のパース
 * @param {string} text - パース対象のテキスト
 * @returns {string} パース後のHTML
 */
function parseInline(text) {
    // インラインコード `code`
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // 太字 **text**
    text = text.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    
    // 下線 __text__
    text = text.replace(/__([^_]+)__/g, '<u>$1</u>');
    
    // 取り消し線 ~~text~~
    text = text.replace(/~~([^~]+)~~/g, '<s>$1</s>');
    
    // リンク [text](url)
    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--accent);">$1</a>');
    
    return text;
}

/**
 * 入れ子引用のパース
 * @param {Array<string>} lines - 引用行の配列
 * @returns {string} パース後のHTML
 */
function parseNestedBlockquote(lines) {
    // 各行の `> ` (スペース含む)の数を数える
    const processedLines = lines.map(line => {
        let level = 0;
        let content = line;
        
        // `> `の個数をカウント
        while (content.startsWith('> ')) {
            level++;
            content = content.substring(2); // '> 'を削除
        }
        
        return { level, content };
    });
    
    // レベルごとにグループ化してHTMLを構築
    function buildQuoteHTML(items, startIndex = 0, currentLevel = 1) {
        let html = '';
        let i = startIndex;
        const contentLines = [];
        
        while (i < items.length) {
            const item = items[i];
            
            if (item.level < currentLevel) {
                break;
            }
            
            if (item.level === currentLevel) {
                contentLines.push(parseInline(item.content));
                i++;
            } else if (item.level > currentLevel) {
                // 子引用を処理
                const childResult = buildQuoteHTML(items, i, currentLevel + 1);
                contentLines.push(childResult.html);
                i = childResult.nextIndex;
            }
        }
        
        html = `<blockquote>${contentLines.join('<br>')}</blockquote>`;
        return { html, nextIndex: i };
    }
    
    const result = buildQuoteHTML(processedLines);
    return result.html;
}

/**
 * リストのパース（箇条書き・番号付き・チェックリスト統合版）
 * @param {Array<string>} items - リストアイテムの配列
 * @returns {string} パース後のHTML
 */
function parseList(items) {
    // 各アイテムの情報を解析
    const parsedItems = items.map(item => {
        const indentMatch = item.match(/^(\s*)/);
        const indent = indentMatch ? indentMatch[1].length : 0;
        const level = Math.floor(indent / 2);
        
        // チェックリストの判定
        const checklistMatch = item.match(/^(\s*)- \[([ x])\]\s(.+)$/);
        if (checklistMatch) {
            const checked = checklistMatch[2] === 'x';
            let content = checklistMatch[3];
            content = content.replace(/  \n/g, '<br>');
            return { level, type: 'checklist', checked, content };
        }
        
        // 番号付きリストの判定
        const isOrdered = /^\s*\d+\.\s/.test(item);
        let content = item.replace(/^\s*(?:[-*]|\d+\.)\s/, '');
        
        // 2スペース改行を<br>に変換
        content = content.replace(/  \n/g, '<br>');
        
        return { level, type: isOrdered ? 'ordered' : 'unordered', content };
    });
    
    // HTMLを構築
    function buildListHTML(items, startIndex = 0, parentLevel = -1) {
        let html = '';
        let i = startIndex;
        
        while (i < items.length) {
            const item = items[i];
            
            // 親レベルより浅い場合は終了
            if (item.level <= parentLevel) {
                break;
            }
            
            // 現在のレベルのアイテムを処理
            if (item.level === parentLevel + 1) {
                if (item.type === 'checklist') {
                    // チェックリスト項目
                    const checkboxId = `checkbox-${Math.random().toString(36).substr(2, 9)}`;
                    html += `<li class="checklist-item"><div class="checklist-content"><input type="checkbox" id="${checkboxId}" ${item.checked ? 'checked' : ''} disabled><label for="${checkboxId}">${parseInline(item.content)}</label></div>`;
                } else {
                    // 通常のリスト項目
                    html += `<li>${parseInline(item.content)}`;
                }
                
                // 次のアイテムが子要素かチェック
                if (i + 1 < items.length && items[i + 1].level > item.level) {
                    const childResult = buildListHTML(items, i + 1, item.level);
                    const childTag = items[i + 1].type === 'ordered' ? 'ol' : 'ul';
                    html += `<${childTag}>${childResult.html}</${childTag}>`;
                    i = childResult.nextIndex - 1;
                }
                
                html += '</li>';
            }
            
            i++;
        }
        
        return { html, nextIndex: i };
    }
    
    // ルートレベルのリストタイプを判定
    const rootType = parsedItems[0].type === 'ordered' ? 'ol' : 'ul';
    const result = buildListHTML(parsedItems);
    
    return `<${rootType}>${result.html}</${rootType}>`;
}

/**
 * マークダウンをHTMLに変換（CSSを含む）
 * @param {string} markdown - マークダウンテキスト
 * @param {Object} options - オプション設定
 * @returns {Promise<Object>} パース後のHTMLとCSS
 */
async function renderMarkdown(markdown, options = {}) {
    const includeCSS = options.includeCSS !== false; // デフォルトでCSS含む
    
    // エスケープ文字の処理用マップ
    const escapeMap = new Map();
    let escapeCounter = 0;
    
    // エスケープされた文字を一時的に置換
    markdown = markdown.replace(/\\(.)/g, (match, char) => {
        const key = `!!ESCAPE!${escapeCounter++}!!`;
        escapeMap.set(key, char);
        return key;
    });
    
    // 空行を<br>に変換
    const markdownLines = markdown.split('\n');
    const processedMarkdown = markdownLines
        .map((line, i) => {
            if (line.trim() === '' && i < markdownLines.length - 1) {
                return '\n!!BR!!';
            }
            return line;
        })
        .join('\n');
    
    let html = processedMarkdown;
    
    // コードブロックを先に処理（```で囲まれた部分）
    const codeBlocks = [];
    html = html.replace(/```([^\n]*)\n([\s\S]*?)```/g, (match, lang, code) => {
        const placeholder = `!!CODEBLOCK!${codeBlocks.length}!!`;
        
        // :::output\n...\n::: 部分を検出
        const outputMatch = code.match(/([\s\S]*?):::output\n([\s\S]*?)\n:::/);
        
        if (outputMatch) {
            // プログラム部分と出力部分を分離
            const programCode = outputMatch[1].trim().replace(/!!BR!!\n/g, '');
            const outputCode = outputMatch[2].trim();
            
            codeBlocks.push(`
                <div class="code-block-container">
                    <pre class="code-program"><code>${escapeHtml(programCode)}</code></pre>
                    <pre class="code-output"><code>${escapeHtml(outputCode)}</code></pre>
                </div>
            `);
        } else {
            // 通常のコードブロック
            codeBlocks.push(`<pre><code>${escapeHtml(code.trim().replace(/!!BR!!\n/g, ''))}</code></pre>`);
        }
        
        return placeholder;
    });
    
    // 画像を処理 ![alt](url)
    const images = [];
    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, url) => {
        const placeholder = `!!IMAGE!${images.length}!!`;
        images.push(`<figure class="article-image"><img src="${escapeHtml(url)}" alt="${escapeHtml(alt)}" />${alt ? `<figcaption>${escapeHtml(alt)}</figcaption>` : ''}</figure>`);
        return placeholder;
    });
    
    // 内部リンク !!text!!(path)
    const internalLinks = [];
    html = html.replace(/!!([^!]+)!!\(([^)]+)\)/g, (match, text, path) => {
        const placeholder = `!!INTERNAL!${internalLinks.length}!!`;
        internalLinks.push(`<span class="internal-link" data-path="${escapeHtml(path)}" style="color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--accent); cursor: pointer;">${escapeHtml(text)}</span>`);
        return placeholder;
    });
    
    // インフォメーションブロック (:::info, :::warn, :::alert)
    const infoBlocks = [];
    html = html.replace(/:::info\n([\s\S]*?)\n:::/g, (match, content) => {
        const placeholder = `!!INFOBLOCK!${infoBlocks.length}!!`;
        infoBlocks.push(`<div class="info-block info-type-info"><div class="info-header">インフォメーション</div><div class="info-content">${escapeHtml(content.trim())}</div></div>`);
        return placeholder;
    });
    html = html.replace(/:::warn\n([\s\S]*?)\n:::/g, (match, content) => {
        const placeholder = `!!INFOBLOCK!${infoBlocks.length}!!`;
        infoBlocks.push(`<div class="info-block info-type-warn"><div class="info-header">注意</div><div class="info-content">${escapeHtml(content.trim())}</div></div>`);
        return placeholder;
    });
    html = html.replace(/:::alert\n([\s\S]*?)\n:::/g, (match, content) => {
        const placeholder = `!!INFOBLOCK!${infoBlocks.length}!!`;
        infoBlocks.push(`<div class="info-block info-type-alert"><div class="info-header">警告</div><div class="info-content">${escapeHtml(content.trim())}</div></div>`);
        return placeholder;
    });
    
    // テーブルを処理
    const tables = [];
    html = html.replace(/(\|[^\n]+\|(\[([^\]]*)\])?\n(?:\|[^\n]+\|\n?)+)/g, (match, tableContent, caption) => {
        let innerCaption = '';
        if (caption !== undefined) {
            innerCaption = caption.replace(/^\[/, '').replace(/\]$/, '');
        }
        const lines = tableContent.trim().split('\n').filter(line => line.trim());
        const placeholder = `!!TABLE!${tables.length}!!`;
        
        // ヘッダー行からキャプション部分を除外
        const headerLine = lines[0].replace(new RegExp(`\\[${innerCaption}\\]`, 'g'), '');
        const headers = headerLine.split('|').filter(cell => cell.trim()).map(h => h.trim());
        
        // アライメント行をスキップ（2行目）
        const alignLine = lines[1];
        const aligns = alignLine.split('|').filter(cell => cell.trim()).map(cell => {
            const trimmed = cell.trim();
            if (trimmed.startsWith(':') && trimmed.endsWith(':')) return 'center';
            if (trimmed.endsWith(':')) return 'right';
            return 'left';
        });
        
        // データ行
        const dataRows = lines.slice(2);
        
        let tableHtml = '<table>';
        if (caption !== undefined) {
            tableHtml += '<caption>' + escapeHtml(innerCaption) + '</caption>';
        }
        tableHtml += '<thead><tr>';
        headers.forEach((header, i) => {
            tableHtml += `<th style="text-align: ${aligns[i] || 'left'}">${parseInline(header)}</th>`;
        });
        tableHtml += '</tr></thead><tbody>';
        
        dataRows.forEach(row => {
            const cells = row.split('|').filter(cell => cell.trim()).map(c => c.trim());
            tableHtml += '<tr>';
            cells.forEach((cell, i) => {
                tableHtml += `<td style="text-align: ${aligns[i] || 'left'}">${parseInline(cell)}</td>`;
            });
            tableHtml += '</tr>';
        });
        
        tableHtml += '</tbody></table>';
        tables.push(tableHtml);
        return placeholder;
    });
    
    // 行ごとに処理
    const lines = html.split('\n');
    const processedLines = [];
    let i = 0;
    
    while (i < lines.length) {
        let line = lines[i];
        
        // 見出しの処理 (# から ###### まで)
        const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
        if (headingMatch) {
            const level = headingMatch[1].length;
            const content = headingMatch[2];
            processedLines.push(`<h${level}>${parseInline(content)}</h${level}>`);
            i++;
            continue;
        }
        
        // 引用の処理 (> で始まる行、入れ子対応)
        if (/^>\s/.test(line)) {
            const quoteLines = [];
            
            while (i < lines.length && /^>\s/.test(lines[i])) {
                quoteLines.push(lines[i]);
                i++;
            }
            
            processedLines.push(parseNestedBlockquote(quoteLines));
            continue;
        }
        
        // リスト（箇条書き・番号付き・チェックリスト）の処理
        if (/^(\s*)[-*]\s/.test(line) || /^(\s*)\d+\.\s/.test(line) || /^(\s*)- \[([ x])\]\s/.test(line)) {
            const listItems = [];
            
            while (i < lines.length && (/^(\s*)[-*]\s/.test(lines[i]) || /^(\s*)\d+\.\s/.test(lines[i]) || /^(\s*)- \[([ x])\]\s/.test(lines[i]) || /^(\s*)\S/.test(lines[i]))) {
                // リスト行または継続行
                if (/^(\s*)[-*]\s/.test(lines[i]) || /^(\s*)\d+\.\s/.test(lines[i]) || /^(\s*)- \[([ x])\]\s/.test(lines[i])) {
                    listItems.push(lines[i]);
                } else if (listItems.length > 0 && lines[i - 1] && lines[i - 1].endsWith('  ')) {
                    // 前の行が2スペースで終わっている場合、継続行として結合
                    listItems[listItems.length - 1] += '\n' + lines[i];
                } else {
                    // リストが終了
                    break;
                }
                i++;
            }
            
            processedLines.push(parseList(listItems));
            continue;
        }
        
        // インライン要素の処理
        line = parseInline(line);
        
        processedLines.push(`<p>${line}</p>`);
        i++;
    }
    
    html = processedLines.join('\n');
    
    // プレースホルダーを戻す
    codeBlocks.forEach((block, i) => {
        html = html.replace(`!!CODEBLOCK!${i}!!`, block);
    });
    images.forEach((img, i) => {
        html = html.replace(`!!IMAGE!${i}!!`, img);
    });
    internalLinks.forEach((link, i) => {
        html = html.replace(`!!INTERNAL!${i}!!`, link);
    });
    infoBlocks.forEach((block, i) => {
        html = html.replace(`!!INFOBLOCK!${i}!!`, block);
    });
    tables.forEach((table, i) => {
        html = html.replace(`!!TABLE!${i}!!`, table);
    });
    
    // <br>マーカーを変換
    html = html.replace(/!!BR!!/g, '<br>');
    
    // エスケープされた文字を戻す
    escapeMap.forEach((value, key) => {
        html = html.replace(new RegExp(key, 'g'), value);
    });
    
    // CSSを取得
    const css = includeCSS ? getMonoMDCSS() : '';
    
    // HTMLをラップ
    const wrappedHtml = `<div class="monomd-body">${html}</div>`;
    
    return {
        html: wrappedHtml,
        css: css,
        fullHTML: includeCSS ? `<style>${css}</style>${wrappedHtml}` : wrappedHtml
    };
}

/**
 * MonoMD用のCSSを取得
 * @returns {string} CSS文字列
 */
function getMonoMDCSS() {
    return `
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css');

:root {
    --cream: #faf8f3;
    --ink: #1a1a1a;
    --accent: #d4532f;
    --muted: #6b6b6b;
    --border: #e0ddd5;
}

.monomd-body {
    line-height: 1.9;
    text-align: left;
}

.monomd-body p {
    margin-bottom: 0;
}

.monomd-body h1,
.monomd-body h2,
.monomd-body h3,
.monomd-body h4 {
    font-family: 'Meiryo', 'メイリオ', sans-serif;
    margin-top: 0;
    margin-bottom: 0;
    font-weight: 600;
}

.monomd-body h1 { font-size: 32px; }
.monomd-body h2 { font-size: 26px; }
.monomd-body h3 { font-size: 22px; }

.monomd-body h5,
.monomd-body h6 {
    font-family: 'Meiryo', 'メイリオ', sans-serif;
    margin-top: 0;
    margin-bottom: 0;
    font-weight: 600;
}

.monomd-body code {
    background: #f0ede4;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: 'Courier New', monospace;
    font-size: 0.9em;
    color: var(--accent);
}

.monomd-body pre {
    background: #2d2d2d;
    color: #f8f8f2;
    padding: 20px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 0 0;
    line-height: 1.6;
}

.monomd-body pre code {
    background: none;
    padding: 0;
    color: inherit;
    font-size: 14px;
}

/* コードブロックコンテナ（プログラム + 出力） */
.monomd-body .code-block-container {
    margin: 0;
}

.monomd-body .code-block-container .code-program {
    border-radius: 8px 8px 0 0;
    margin-bottom: 0;
}

.monomd-body .code-block-container .code-output {
    background: #e8e8e8;
    color: #333333;
    border-radius: 0 0 8px 8px;
    margin-top: 0;
    border-top: 2px solid #cccccc;
}

/* インフォメーションブロック */
.monomd-body .info-block {
    padding: 15px;
    border-radius: 8px;
    margin: 0;
    color: #ffffff;
}

.monomd-body .info-block .info-header {
    font-weight: 600;
    margin-bottom: 10px;
    font-size: 16px;
}

.monomd-body .info-block .info-header::before {
    font-family: "Font Awesome 5 Free";
    font-weight: 900;
    margin-right: 8px;
}

.monomd-body .info-block .info-content {
    line-height: 1.6;
    white-space: pre-wrap;
}

/* インフォメーション（緑） */
.monomd-body .info-type-info {
    background: #4cb100;
}

.monomd-body .info-type-info .info-header::before {
    content: "\\f058";
}

/* 注意（黄色） */
.monomd-body .info-type-warn {
    background: #e0af00;
    color: #ffffff;
}

.monomd-body .info-type-warn .info-header::before {
    content: "\\f06a";
}

/* 警告（赤） */
.monomd-body .info-type-alert {
    background: #dc3545;
}

.monomd-body .info-type-alert .info-header::before {
    content: "\\f057";
}

.monomd-body ul,
.monomd-body ol {
    margin-left: 1.5em;
    margin-bottom: 0;
}

.monomd-body li {
    margin-bottom: 0;
}

/* チェックリストスタイル */
.monomd-body .checklist-item {
    list-style: none;
}

.monomd-body .checklist-content {
    display: flex;
    align-items: flex-start;
    margin-left: -25px;
}

.monomd-body .checklist-content input[type="checkbox"] {
    margin-right: 8px;
    margin-top: 9px;
    flex-shrink: 0;
}

.monomd-body .checklist-content label {
    cursor: default;
}

.monomd-body blockquote {
    border-left: 4px solid var(--border);
    padding-left: 20px;
    margin: 0;
    font-style: italic;
    color: var(--muted);
}

.monomd-body a {
    color: var(--accent);
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.2s;
}

.monomd-body a:hover {
    border-bottom-color: var(--accent);
}

/* テーブルスタイル */
.monomd-body table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.5em 0;
}

.monomd-body table caption {
    caption-side: bottom;
    margin-top: 8px;
    font-size: 14px;
    color: var(--ink);
    text-align: center;
}

.monomd-body table th,
.monomd-body table td {
    border: 1px solid var(--border);
    padding: 8px 12px;
}

.monomd-body table th {
    background-color: #f5f3ed;
    font-weight: 600;
}

/* 画像スタイル */
.article-image {
    margin: 0 auto;
    text-align: center;
}

.article-image img {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
    display: block;
    margin: 0 auto;
    margin-bottom: 0;
}

.article-image figcaption {
    margin-top: 12px;
    font-family: 'Meiryo', 'メイリオ', sans-serif;
    font-size: 14px;
    color: var(--ink);
}
`;
}

// Node.js環境とブラウザ環境の両方をサポート
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        renderMarkdown,
        parseInline,
        parseList,
        parseNestedBlockquote,
        escapeHtml,
        getMonoMDCSS
    };
} else if (typeof window !== 'undefined') {
    window.MonoMD = {
        renderMarkdown,
        parseInline,
        parseList,
        parseNestedBlockquote,
        escapeHtml,
        getMonoMDCSS
    };
}