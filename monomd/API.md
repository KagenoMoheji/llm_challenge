# MonoMD API Reference

Complete API documentation for MonoMD.

## Table of Contents

- [Main Functions](#main-functions)
  - [renderMarkdown()](#rendermarkdownmarkdown-options)
  - [parseInline()](#parseinlinetext)
  - [parseList()](#parselistitems)
  - [parseNestedBlockquote()](#parsenestedblockquotelines)
  - [escapeHtml()](#escapehtmltext)
  - [getMonoMDCSS()](#getmonomdcss)
- [Return Types](#return-types)
- [Options](#options)
- [Advanced Usage](#advanced-usage)

---

## Main Functions

### `renderMarkdown(markdown, options)`

Converts Markdown text to HTML with CSS.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `markdown` | string | ✅ Yes | - | The Markdown text to parse |
| `options` | Object | ❌ No | `{}` | Parsing options |

**Options Object:**

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `includeCSS` | boolean | `true` | Include CSS in output |

**Returns:** `Promise<MarkdownResult>`

```typescript
interface MarkdownResult {
  html: string;      // HTML wrapped in <div class="monomd-body">
  css: string;       // CSS string (includes Font Awesome CDN)
  fullHTML: string;  // Combined <style> + HTML
}
```

**Example:**

```javascript
const { renderMarkdown } = require('monomd');

// Basic usage
const result = await renderMarkdown('# Hello World');
console.log(result.html);
// <div class="monomd-body"><h1>Hello World</h1></div>

// Without CSS
const resultNoCSS = await renderMarkdown('# Hello', { includeCSS: false });
console.log(resultNoCSS.css);
// '' (empty string)

// Using fullHTML
const fullResult = await renderMarkdown('# Title\n\nContent');
document.body.innerHTML = fullResult.fullHTML;
```

---

### `parseInline(text)`

Parses inline Markdown elements (bold, underline, code, links, etc.).

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `text` | string | ✅ Yes | Text containing inline Markdown |

**Returns:** `string` - Parsed HTML

**Supported Inline Elements:**

| Markdown | HTML Output | Notes |
|----------|-------------|-------|
| `**bold**` | `<b>bold</b>` | Bold text |
| `__underline__` | `<u>underline</u>` | Underline (NOT italic!) |
| `~~strike~~` | `<s>strike</s>` | Strikethrough |
| `` `code` `` | `<code>code</code>` | Inline code |
| `[text](url)` | `<a href="url">text</a>` | Link with `target="_blank"` |

**Example:**

```javascript
const { parseInline } = require('monomd');

const text = 'This is **bold** and __underlined__.';
const html = parseInline(text);
// 'This is <b>bold</b> and <u>underlined</u>.'

const link = parseInline('[Google](https://google.com)');
// '<a href="https://google.com" target="_blank">Google</a>'
```

---

### `parseList(items)`

Parses list items (unordered, ordered, and checklists).

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `items` | Array<string> | ✅ Yes | Array of list item strings |

**Returns:** `string` - Parsed HTML list

**Supported List Types:**

- **Unordered**: `- item` or `* item`
- **Ordered**: `1. item`
- **Checklist**: `- [ ] item` or `- [x] item`
- **Nested**: Use 2-space indentation

**Example:**

```javascript
const { parseList } = require('monomd');

const items = [
  '- Item 1',
  '- Item 2',
  '  - Nested item',
  '- Item 3'
];

const html = parseList(items);
// <ul><li>Item 1</li><li>Item 2<ul><li>Nested item</li></ul></li><li>Item 3</li></ul>

// Mixed list types (v1.0.1+)
const mixedItems = [
  '1. Ordered item',
  '  - Unordered nested',
  '  - [ ] Checklist nested',
  '- Unordered item'
];

const mixedHtml = parseList(mixedItems);
// Correctly handles mixed types!
```

**Note:** In v1.0.1+, the parser intelligently handles mixed list types and properly closes/opens lists when types change.

---

### `parseNestedBlockquote(lines)`

Parses nested blockquotes.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `lines` | Array<string> | ✅ Yes | Array of quote lines |

**Returns:** `string` - Parsed HTML blockquote

**Example:**

```javascript
const { parseNestedBlockquote } = require('monomd');

const lines = [
  '> Level 1',
  '> > Level 2',
  '> > > Level 3'
];

const html = parseNestedBlockquote(lines);
// <blockquote>Level 1<br><blockquote>Level 2<br><blockquote>Level 3</blockquote></blockquote></blockquote>
```

---

### `escapeHtml(text)`

Escapes HTML special characters to prevent XSS attacks.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `text` | string | ✅ Yes | Text to escape |

**Returns:** `string` - Escaped text

**Escaped Characters:**

- `&` → `&amp;`
- `<` → `&lt;`
- `>` → `&gt;`
- `"` → `&quot;`
- `'` → `&#039;`

**Example:**

```javascript
const { escapeHtml } = require('monomd');

const unsafe = '<script>alert("XSS")</script>';
const safe = escapeHtml(unsafe);
// '&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;'
```

---

### `getMonoMDCSS()`

Returns the CSS string for MonoMD styling.

**Parameters:** None

**Returns:** `string` - CSS string including Font Awesome CDN import

**Example:**

```javascript
const { getMonoMDCSS } = require('monomd');

const css = getMonoMDCSS();
console.log(css.includes('@import'));  // true
console.log(css.includes('.monomd-body'));  // true

// Add CSS to page
const style = document.createElement('style');
style.textContent = getMonoMDCSS();
document.head.appendChild(style);
```

**CSS Includes:**

- Font Awesome 5 CDN import
- `.monomd-body` wrapper styles
- Heading styles (h1-h6)
- Code block styles (with/without output)
- Table styles (with caption support)
- List styles (including checklists)
- Information block styles (info, warn, alert)
- Blockquote styles
- Image styles (with caption)

---

## Return Types

### MarkdownResult

The object returned by `renderMarkdown()`:

```typescript
interface MarkdownResult {
  html: string;      // HTML content wrapped in <div class="monomd-body">
  css: string;       // CSS stylesheet string
  fullHTML: string;  // Complete HTML: <style> + <div>
}
```

**Usage Examples:**

```javascript
const result = await renderMarkdown('# Title');

// Option 1: Use fullHTML (easiest)
document.body.innerHTML = result.fullHTML;

// Option 2: Separate CSS and HTML
document.head.insertAdjacentHTML('beforeend', `<style>${result.css}</style>`);
document.body.innerHTML = result.html;

// Option 3: Custom CSS placement
const customCSS = result.css.replace('--accent: #d4532f', '--accent: #0066cc');
document.head.insertAdjacentHTML('beforeend', `<style>${customCSS}</style>`);
document.body.innerHTML = result.html;
```

---

## Options

### RenderMarkdown Options

```typescript
interface RenderOptions {
  includeCSS?: boolean;  // Default: true
}
```

**Example:**

```javascript
// Include CSS (default)
const withCSS = await renderMarkdown('# Title');
console.log(withCSS.css);  // Full CSS string

// Exclude CSS
const withoutCSS = await renderMarkdown('# Title', { includeCSS: false });
console.log(withoutCSS.css);  // Empty string ''
```

---

## Advanced Usage

### Custom Styling

Override CSS variables:

```javascript
const result = await renderMarkdown('# Hello');

// Customize colors
const customCSS = result.css
  .replace('--accent: #d4532f', '--accent: #0066cc')
  .replace('--ink: #1a1a1a', '--ink: #333333');

document.head.insertAdjacentHTML('beforeend', `<style>${customCSS}</style>`);
```

### React Integration

```jsx
import { renderMarkdown } from 'monomd';
import { useEffect, useState } from 'react';

function MarkdownViewer({ markdown }) {
  const [html, setHtml] = useState('');
  const [cssLoaded, setCssLoaded] = useState(false);

  useEffect(() => {
    renderMarkdown(markdown).then(result => {
      // Add CSS once
      if (!cssLoaded) {
        const style = document.createElement('style');
        style.textContent = result.css;
        document.head.appendChild(style);
        setCssLoaded(true);
      }
      setHtml(result.html);
    });
  }, [markdown, cssLoaded]);

  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
```

### Vue Integration

```vue
<template>
  <div v-html="html"></div>
</template>

<script>
import { renderMarkdown } from 'monomd';

export default {
  props: ['markdown'],
  data() {
    return {
      html: ''
    };
  },
  watch: {
    markdown: {
      immediate: true,
      async handler(newMarkdown) {
        const result = await renderMarkdown(newMarkdown);
        
        // Add CSS if not already added
        if (!document.getElementById('monomd-css')) {
          const style = document.createElement('style');
          style.id = 'monomd-css';
          style.textContent = result.css;
          document.head.appendChild(style);
        }
        
        this.html = result.html;
      }
    }
  }
};
</script>
```

### Server-Side Rendering (SSR)

```javascript
const { renderMarkdown } = require('monomd');

// Express.js example
app.get('/article/:id', async (req, res) => {
  const article = await getArticle(req.params.id);
  const result = await renderMarkdown(article.content);
  
  res.send(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>${article.title}</title>
      <style>${result.css}</style>
    </head>
    <body>
      ${result.html}
    </body>
    </html>
  `);
});
```

### Batch Processing

```javascript
const articles = [
  '# Article 1\n\nContent...',
  '# Article 2\n\nContent...',
  '# Article 3\n\nContent...'
];

// Process all articles
const results = await Promise.all(
  articles.map(md => renderMarkdown(md))
);

// Get CSS once (it's the same for all)
const css = results[0].css;

// Use HTML for each article
results.forEach((result, i) => {
  console.log(`Article ${i + 1}:`, result.html);
});
```

---

## Environment Support

### Node.js

All functions work in Node.js environment.

```javascript
const MonoMD = require('monomd');
const { renderMarkdown } = MonoMD;
```

### Browser

All functions are available via `window.MonoMD`:

```html
<script src="node_modules/monomd/index.js"></script>
<script>
  MonoMD.renderMarkdown('# Hello').then(result => {
    // Use result
  });
</script>
```

### ES Modules (Future)

Currently not supported. Use CommonJS or browser globals.

---

## Performance Tips

1. **Cache CSS**: Get CSS once and reuse it
   ```javascript
   const css = getMonoMDCSS();
   // Reuse for all renders
   ```

2. **Batch operations**: Process multiple documents in parallel
   ```javascript
   await Promise.all(documents.map(renderMarkdown));
   ```

3. **Avoid re-renders**: Only call `renderMarkdown()` when content changes

---

## Version History

- **v1.0.1**: Improved list parsing for mixed types
- **v1.0.0**: Initial release

For detailed changes, see [CHANGELOG.md](CHANGELOG.md).

---

## See Also

- [README.md](README.md) - Package overview
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [example.html](example.html) - Interactive demo

---

**MonoMD API Reference v1.0.1**

*A redundant-free Markdown parser where every symbol has its own unique role.*