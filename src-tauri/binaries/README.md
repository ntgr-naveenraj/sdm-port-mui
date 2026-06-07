# Bundled API binaries for Tauri (`externalBin`)

Tauri expects:

`sdm-api-<rustc-host-triple>.exe` on Windows  
`sdm-api-<rustc-host-triple>` on macOS / Linux  

Examples:

- `sdm-api-x86_64-pc-windows-msvc.exe`
- `sdm-api-aarch64-apple-darwin`
- `sdm-api-x86_64-unknown-linux-gnu`

**Generate before `npm run tauri build` (or rely on `beforeBuildCommand` in `tauri.conf.json`):**

From repo root:

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r backend/requirements.txt -r backend/requirements-build.txt
npm run sidecar:prepare
```

`sidecar-prepare.mjs` runs PyInstaller and copies the artifact here with the correct name.

Do not commit the `sdm-api-*` files (see root `.gitignore`).
