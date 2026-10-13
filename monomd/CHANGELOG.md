# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-02-07

### Changed
- Improved list parsing logic to handle complex nested lists with mixed types (unordered, ordered, checklist)
- Added `s` flag to checklist regex to support multiline content
- Enhanced `buildListHTML` function with `parentType` parameter for better type tracking
- Implemented `flushCurrentList` mechanism to properly close lists when type changes
- Checklists are now processed independently with proper wrapping

### Fixed
- Fixed incorrect nesting when mixing different list types
- Fixed checklist rendering in complex nested structures

## [1.0.0] - 2026-02-07

### Added
- Initial release of MonoMD
- Redundant-free Markdown parsing where every symbol has its own unique role
- Support for headings (H1-H6)
- Text formatting:
  - Bold (`**text**`)
  - Underline (`__text__` - unique role, not italic!)
  - Strikethrough (`~~text~~`)
  - Inline code (`` `code` ``)
- Lists support:
  - Unordered lists
  - Ordered lists
  - Nested lists
  - Checklists (`- [ ]` / `- [x]`)
- Links:
  - Standard links (`[text](url)`)
  - Internal links (`!!text!!(path)`)
- Images with captions (`![caption](url)`)
- Code blocks:
  - Simple code blocks (` ```language `)
  - Code blocks with output sections (`:::output`)
- Tables:
  - Standard tables with alignment
  - Tables with captions (`[caption]`)
- Blockquotes:
  - Simple blockquotes
  - Nested blockquotes
- Information blocks:
  - Info blocks (`:::info`)
  - Warning blocks (`:::warn`)
  - Alert blocks (`:::alert`)
- Escaped characters support (`\*`, `\[`, etc.)
- Automatic line break conversion
- HTML escaping for security
- CSS included with `.monomd-body` class
- Works in both Node.js and browser environments
- Zero dependencies
- Comprehensive test suite (20 tests)
- Interactive browser demo