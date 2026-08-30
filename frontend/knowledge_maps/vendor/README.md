# web/vendor/

Third-party browser libraries vendored into the repo so the student UI works
**fully offline** (no CDN at runtime). Served by FastAPI at `/static/vendor/*`
(see `app/main.py` static mount of `web/`).

## d3.v7.min.js

| | |
|---|---|
| Library | [D3.js](https://d3js.org/) |
| Version | 7.9.0 |
| Build | UMD (`dist/d3.min.js`) — defines `window.d3` in the browser, `module.exports` under Node |
| Source | `https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js` |
| Size | ~280 KB |
| SRI (sha384) | `sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i` |
| sha256 | `f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539` |

Used only by the mind-map renderer (`web/mindmap-render.js`) —
`d3.hierarchy`, `d3.tree`, `d3.linkRadial`, `d3.zoom`, `d3.select`,
`d3.transition`.

### Updating

```bash
curl -sSL -o web/vendor/d3.v7.min.js \
  "https://cdn.jsdelivr.net/npm/d3@<version>/dist/d3.min.js"
openssl dgst -sha384 -binary web/vendor/d3.v7.min.js | openssl base64 -A   # refresh SRI above
node -e "const d3=require('./web/vendor/d3.v7.min.js'); console.log(d3.version)"
```
