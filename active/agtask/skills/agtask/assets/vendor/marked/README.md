# Marked browser bundle

This directory vendors `marked` 18.0.7 from the published npm package so the
local dashboard remains self-contained and compatible with its `script-src
'self'` content security policy.

- Source: <https://www.npmjs.com/package/marked/v/18.0.7>
- File: `package/lib/marked.umd.js`
- SHA-256: `7a1f8c5e7226b75ff16644bdb2c0130d2ae7371e7ea3106c2d6dac77ab0ff7b6`
- License: MIT; see `LICENSE`

The dashboard uses Marked only to tokenize Markdown. Ledger content is not
inserted as renderer-produced HTML; `task.js` constructs an allowlisted DOM
tree and validates link destinations.
