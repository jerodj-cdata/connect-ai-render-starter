# Vendored browser libraries

Served from here instead of a CDN, so the chat page works offline and behind
firewalls, and a compromised CDN can't change it. Copied unmodified from the
npm registry tarballs.

| File | Package | License | SHA-256 |
| --- | --- | --- | --- |
| `marked.umd.js` | [marked](https://github.com/markedjs/marked) 18.0.14, `lib/marked.umd.js` | MIT ([LICENSE-marked.txt](LICENSE-marked.txt)) | `21568877a938d2c4e7d74e27f18e60da96bb73a68809610ca39216e1efebae62` |
| `purify.min.js` | [DOMPurify](https://github.com/cure53/DOMPurify) 3.4.16, `dist/purify.min.js` | Apache-2.0 or MPL-2.0 ([LICENSE-dompurify.txt](LICENSE-dompurify.txt)) | `2c90a9b46d6463f26038a29b686e82bc91de01fdac9d5229e7cfe3b360134ea2` |

To update, download the new tarball (`https://registry.npmjs.org/<name>/-/<name>-<version>.tgz`),
copy the same file over, and update this table. DOMPurify is the chat page's
XSS defence, so keep it current.
