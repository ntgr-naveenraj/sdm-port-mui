# Release checklist (SDM_Modern)

Use this when cutting a version for wider distribution (installers, internal shares, etc.).

## 1. Version

- Bump **`package.json`** `version` if you track the web app semver there.
- Align **Tauri** version in `src-tauri/tauri.conf.json` / `Cargo.toml` if your process requires it.

## 2. Web production build

From repo root:

```bash
npm ci
npm run build
```

Output: `dist/` (suitable for static hosting if you deploy only the UI; the Flask API must still be reachable).

## 3. Desktop installer (Tauri + API sidecar)

Full prerequisites: [PACKAGING.md](PACKAGING.md) (Rust, Node, Python, PyInstaller; MSVC on Windows).

From repo root on **each OS** you ship:

```bash
pip install -r backend/requirements.txt -r backend/requirements-build.txt
npm ci
npm run sidecar:prepare
npm run tauri build
```

Artifacts (varies by OS): under `src-tauri/target/release/bundle/` (e.g. `.msi`, `.dmg`, `.AppImage`).

`tauri.conf.json` may run `npm run build` and `sidecar:prepare` as pre-steps; confirm sidecar exists under `src-tauri/binaries/` before distributing.

## 4. Signing & distribution

- **macOS:** Plan for code signing + notarization for broad distribution; unsigned builds often need “Open” from context menu the first time.
- **Windows:** Follow your org’s code-signing policy for installers.
- **Upload:** Publish to GitHub Releases, internal artifact store, or MDM — per your team.

## 5. Changelog

Update [CHANGELOG.md](../CHANGELOG.md) with the version, date, and user-visible changes.

## 6. Smoke test the artifact

- Install or run the produced bundle on a clean machine (or VM).
- Confirm the bundled API starts (default port **8000**) and the UI loads and authenticates against your test environment.
