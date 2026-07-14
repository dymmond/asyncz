# Dashboard Vendor Assets

Asyncz vendors dashboard browser assets as package resources so the contrib
dashboard does not depend on public CDNs at runtime.

## Current Assets

| Asset | Version | Source | Runtime file |
| --- | --- | --- | --- |
| Alpine.js CSP | 3.15.12 | npm `@alpinejs/csp` | `vendor/alpinejs/alpine-csp-3.15.12.min.js` |
| Tailwind CSS | 4.3.2 | npm `tailwindcss` + `@tailwindcss/cli` | `css/tailwind-4.3.2.min.css` |
| HTMX | 1.9.12 | npm `htmx.org` | `vendor/htmx/htmx-1.9.12.min.js` |
| Toastify | 1.6.1 | npm `toastify-js` | `js/toastify.min.js`, `css/toastify.min.css` |

Checksums and npm integrity strings are recorded in `manifest.json`.
License attributions are stored in `vendor/licenses/`.

## Update Procedure

1. Query authoritative npm package metadata for the exact packages recorded in
   `manifest.json`.
2. Download the exact tarballs listed in the metadata and verify their npm
   integrity values plus SHA-256 checksums.
3. Copy `@alpinejs/csp`'s `dist/cdn.min.js` to
   `vendor/alpinejs/alpine-csp-<version>.min.js`.
4. Copy `htmx.org`'s `dist/htmx.min.js` to
   `vendor/htmx/htmx-<version>.min.js`.
5. Generate Tailwind's committed stylesheet from `css/asyncz-tailwind.input.css`
   using the matching `@tailwindcss/cli` and `tailwindcss` versions. The output
   must be written to `css/tailwind-<version>.min.css`.
6. Update template references, `manifest.json`, and license files.
7. Run dashboard static-asset tests and build a wheel/sdist to prove every asset
   is included from an installed package.

Do not replace these assets with public CDN links.
