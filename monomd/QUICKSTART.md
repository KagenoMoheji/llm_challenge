# MonoMD Quick Start Guide

Get started with MonoMD in under 5 minutes! 🚀

## Installation

```bash
npm install monomd
```

## Basic Usage

### Node.js

```javascript
const { renderMarkdown } = require('monomd');

const markdown = `
# Hello MonoMD

This is **bold** and this is __underlined__.
`;

renderMarkdown(markdown).then(result => {
  console.log(result.html);
  // Output: <div class="monomd-body"><h1>Hello MonoMD</h1><p>This is <b>bold</b> and this is <u>underlined</u>.</p></div>
});
```

### Browser

```html
<!DOCTYPE html>
<html>
<head>
  <title>MonoMD Demo</title>
</head>
<body>
  <div id="output"></div>
  
  <script src="node_modules/monomd/index.js"></script>
  <script>
    const markdown = '# Hello MonoMD\n\nThis is **bold** text.';
    
    MonoMD.renderMarkdown(markdown).then(result => {
      // Add CSS to head
      document.head.insertAdjacentHTML('beforeend', `<style>${result.css}</style>`);
      // Display HTML
      document.getElementById('output').innerHTML = result.html;
    });
  </script>
</body>
</html>
```

## Common Examples

### 1. Simple Blog Post

```javascript
const post = `
# My First Post

Published: 2026-02-07

## Introduction

Welcome to my blog! Here's what you'll learn:

- **Markdown basics**
- __Text formatting__
- ~~Common mistakes~~

## Code Example

\`\`\`javascript
console.log('Hello, World!');
\`\`\`

That's it!
`;

renderMarkdown(post).then(result => {
  document.getElementById('blog').innerHTML = result.fullHTML;
});
```

### 2. Documentation

```javascript
const docs = `
# API Documentation

## \`getData(id)\`

Retrieves data by ID.

**Parameters:**
- \`id\` (string): Unique identifier

**Returns:**
- Object: The data
`;

renderMarkdown(docs).then(result => {
  // CSS is included in result.fullHTML
  document.getElementById('docs').innerHTML = result.fullHTML;
});
```

### 3. Task List

```javascript
const tasks = `
# My Tasks

- [x] Learn MonoMD
- [ ] Build a blog
- [ ] Deploy to production
`;

renderMarkdown(tasks).then(result => {
  document.getElementById('tasks').innerHTML = result.fullHTML;
});
```

## Understanding the Output

The `renderMarkdown()` function returns an object with three properties:

```javascript
{
  html: '<div class="monomd-body">...</div>',  // HTML with wrapper
  css: '/* CSS styles */',                      // CSS string
  fullHTML: '<style>...</style><div>...</div>'  // Combined HTML + CSS
}
```

**Which one to use?**

- Use `fullHTML` when you want everything in one go
- Use `html` + `css` separately when you need more control

## Unique Syntax

MonoMD uses unique symbols to avoid confusion:

| Syntax | Output | Note |
|--------|--------|------|
| `**bold**` | **bold** | Bold text |
| `__underline__` | <u>underline</u> | Underline (NOT italic!) |
| `~~strike~~` | ~~strike~~ | Strikethrough |
| `` `code` `` | `code` | Inline code |

## Advanced Features

### Internal Links

```markdown
!!Article Title!!(/articles/2019/1)
```

### Code with Output

````markdown
```python
print("Hello")
:::output
Hello
:::
```
````

### Tables with Captions

```markdown
| Name | Age |[Employee Data]
|------|-----|
| Alice | 25 |
```

### Information Blocks

```markdown
:::info
This is important information!
:::

:::warn
Be careful with this!
:::

:::alert
Critical warning!
:::
```

## Next Steps

- Read the [README](README.md) for complete feature list
- Check [API.md](API.md) for detailed function reference
- See [example.html](example.html) for interactive demo

## Need Help?

- **Issues**: Report bugs on GitHub
- **Documentation**: See README.md and API.md
- **Examples**: Open example.html in your browser

---

**Happy coding with MonoMD!** 🎉

*A redundant-free Markdown parser where every symbol has its own unique role.*