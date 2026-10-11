# Vendored third-party files

Shipped with the app so that nothing is loaded from external providers at runtime (REQUIREMENTS
8.3). Wired together by the import map in `momato/static/index.html`.

| Path | Package | Version | License | Source file |
|---|---|---|---|---|
| `preact/preact.module.js` | preact | 10.29.8 | MIT (`preact/LICENSE`) | `dist/preact.module.js` |
| `preact/hooks.module.js` | preact | 10.29.8 | MIT | `hooks/dist/hooks.module.js` |
| `htm/htm.module.js` | htm | 3.1.1 | Apache-2.0 (`htm/LICENSE`) | `dist/htm.module.js` |
| `../fonts/bricolage-grotesque-*.woff2` | @fontsource-variable/bricolage-grotesque | 5.3.0 | SIL OFL 1.1 (`../fonts/LICENSE-OFL.txt`) | `files/bricolage-grotesque-latin{,-ext}-opsz-normal.woff2` |
| `../fonts/figtree-*.woff2` | @fontsource-variable/figtree | 5.3.0 | SIL OFL 1.1 | `files/figtree-latin{,-ext}-wght-normal.woff2` |
| `../fonts/ibm-plex-sans-*.woff2` | @fontsource/ibm-plex-sans | 5.3.0 | SIL OFL 1.1 | `files/ibm-plex-sans-latin{,-ext}-{400,500,600,700}-normal.woff2` |

To update: `npm pack <package>@<version>` in a scratch folder, extract it into its own folder, copy
the files listed above, update this table, run the browser tests.
