# MonoMD

**A redundant-free Markdown parser where every symbol has its own unique role.**

MonoMD is a unique Markdown parser that ensures each symbol has a distinct purpose, eliminating redundancy in syntax. Unlike traditional Markdown parsers that allow multiple ways to express the same formatting (like `*italic*` and `_italic_`), MonoMD assigns each symbol its own specific role.

## 🎯 Philosophy

**Every symbol has its own unique role:**
- `**text**` = Bold
- `__text__` = Underline (not italic!)
- `~~text~~` = Strikethrough
- `` `code` `` = Inline code
- `![alt](url)` = Images with optional captions
- `!!text!!(path)` = Internal links
- `- [ ]` / `- [x]` = Checkboxes
- `:::info` / `:::warn` / `:::alert` = Information blocks
- Code blocks with `:::output` = Code with output sections
- Tables with `[caption]` = Tables with captions

## ✨ Features

- 🎨 **CSS Included** - Styled HTML output ready to use
- 🚀 **Zero Dependencies** - Lightweight and fast
- 🌐 **Universal** - Works in Node.js and browsers
- 📦 **Complete** - Handles complex Markdown features
- 🎯 **No Redundancy** - Each symbol has one purpose

## 📖 Documentation

- **[Quick Start Guide](QUICKSTART.md)** - Get started in 5 minutes
- **[API Reference](API.md)** - Complete API documentation
- **[Changelog](CHANGELOG.md)** - Version history and changes
- **[Interactive Demo](example.html)** - Try it in your browser

## 📦 Installation

```bash
npm install monomd
```

## 🚀 Quick Start

### Node.js

```javascript
const { renderMarkdown } = require('monomd');

const markdown = `
# Hello MonoMD

This is **bold**, this is __underlined__, and this is ~~strikethrough~~.

- Item 1
- Item 2
  - Nested item
`;

renderMarkdown(markdown).then(result => {
  console.log(result.html);  // HTML with wrapper
  console.log(result.css);   // Accompanying CSS
  console.log(result.fullHTML);  // HTML + CSS combined
});
```

### Browser

```html
<!DOCTYPE html>
<html>
<head>
  <title>MonoMD Demo</title>
  <script src="node_modules/monomd/index.js"></script>
</head>
<body>
  <div id="output"></div>

  <script>
    const markdown = '# Hello World\n\nThis is **bold** text.';
    
    MonoMD.renderMarkdown(markdown).then(result => {
      // Insert HTML and CSS
      document.head.insertAdjacentHTML('beforeend', `<style>${result.css}</style>`);
      document.getElementById('output').innerHTML = result.html;
    });
  </script>
</body>
</html>
```

## 📚 Supported Syntax

### Headings

```markdown
# H1
## H2
### H3
#### H4
##### H5
###### H6
```

### Text Formatting

```markdown
**bold text**        → Bold
__underline text__   → Underline
~~strikethrough~~    → Strikethrough
`inline code`        → Code
```

### Lists

**Unordered Lists:**
```markdown
- Item 1
- Item 2
  - Nested item
```

**Ordered Lists:**
```markdown
1. First
2. Second
3. Third
```

**Checklists:**
```markdown
- [ ] Unchecked item
- [x] Checked item
```

### Links and Images

**External Links:**
```markdown
[Link text](https://example.com)
```

**Internal Links (Custom):**
```markdown
!!Article Title!!(/articles/2019/1)
```

**Images with Captions:**
```markdown
![This is a caption](https://example.com/image.jpg)
```

### Code Blocks

**Simple Code Block:**
````markdown
```javascript
const hello = 'world';
console.log(hello);
```
````

**Code Block with Output:**
````markdown
```python
print("Hello, World!")
:::output
Hello, World!
:::
```
````

### Tables

**Simple Table:**
```markdown
| Name | Age | City |
|------|:---:|-----:|
| Alice | 25 | Tokyo |
| Bob | 30 | Osaka |
```

**Table with Caption:**
```markdown
| Name | Age |[Employee Data]
|------|-----|
| Alice | 25 |
| Bob | 30 |
```

### Blockquotes

**Simple Quote:**
```markdown
> This is a quote
```

**Nested Quotes:**
```markdown
> Level 1
> > Level 2
> > > Level 3
```

### Information Blocks

```markdown
:::info
This is an information message
:::

:::warn
This is a warning message
:::

:::alert
This is an alert message
:::
```

### Special Features

**Escaped Characters:**
```markdown
\*Not bold\* → *Not bold*
```

**Line Breaks:**
```markdown
Empty lines become <br> tags automatically
```

## 🎨 CSS Styling

MonoMD includes beautiful default CSS styling. The output is wrapped in `.monomd-body` class:

```html
<div class="monomd-body">
  <!-- Rendered markdown content -->
</div>
```

You can customize the CSS by overriding CSS variables:

```css
:root {
    --cream: #faf8f3;
    --ink: #1a1a1a;
    --accent: #d4532f;
    --muted: #6b6b6b;
    --border: #e0ddd5;
}
```

## 📖 API

### `renderMarkdown(markdown, options)`

Converts Markdown to HTML with CSS.

**Parameters:**
- `markdown` (string): Markdown text
- `options` (Object): Optional settings
  - `includeCSS` (boolean): Include CSS (default: true)

**Returns:** Promise<Object>
```javascript
{
  html: '<div class="monomd-body">...</div>',
  css: '/* CSS styles */',
  fullHTML: '<style>...</style><div class="monomd-body">...</div>'
}
```

### `parseInline(text)`

Parses inline elements (bold, underline, code, links).

**Parameters:**
- `text` (string): Text with inline markdown

**Returns:** string

### `parseList(items)`

Parses list items.

**Parameters:**
- `items` (Array<string>): List item strings

**Returns:** string

### `parseNestedBlockquote(lines)`

Parses nested blockquotes.

**Parameters:**
- `lines` (Array<string>): Quote line strings

**Returns:** string

### `escapeHtml(text)`

Escapes HTML special characters.

**Parameters:**
- `text` (string): Text to escape

**Returns:** string

### `getMonoMDCSS()`

Gets the MonoMD CSS.

**Returns:** string

## 🔧 Advanced Usage

### Without CSS

```javascript
const result = await renderMarkdown(markdown, { includeCSS: false });
// result.css will be empty
```

### Custom CSS

```javascript
const result = await renderMarkdown(markdown);
const customCSS = result.css.replace('--accent: #d4532f', '--accent: #0066cc');
```

## 🌟 Examples

See `example.html` for a live interactive demo.

## 📄 License

MIT License

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 🐛 Issues

Found a bug? Please report it on [GitHub Issues](your-repo-url/issues).

---

**MonoMD** - Where every symbol has its purpose.