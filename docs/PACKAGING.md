# Desktop packaging (Tauri + API sidecar)

The React UI talks to Flask on `http://127.0.0.1:8000`. The packaged app starts a **frozen** Python API next to the executable (Tauri `externalBin`) so users do not run `python` manually.

## Prerequisites

- **Rust** + [Tauri v1 prerequisites](https://v1.tauri.app/v1/guides/getting-started/prerequisites)
- **Node.js** + npm
- **Python 3** with a **virtual environment** (recommended on Ubuntu 24+ — system Python is *externally managed* / PEP 668, so global `pip install` is blocked):

  ```bash
  python3 -m venv .venv
  source .venv/bin/activate   # Windows: .venv\Scripts\activate
  python -m pip install -U pip setuptools wheel
  python -m pip install -r backend/requirements.txt -r backend/requirements-build.txt
  ```

  Always use **`python -m pip`** (after activating) so you never accidentally call the **system** `pip` (PEP 668). Check: `command -v python` should show `.../.venv/bin/python`.

  Keep the venv **activated** in the terminal where you run `npm run sidecar:prepare` or `npm run tauri build` so PyInstaller uses the right packages.

### Windows: MSVC linker (`link.exe`)

The `x86_64-pc-windows-msvc` toolchain needs the **Visual C++ build tools** (not only `rustup`). If `cargo` works but builds fail with **`linker 'link.exe' not found`**, install the workload below, then open a **new** terminal.

**Option A — winget (run PowerShell as Administrator; install can take 10–30+ minutes):**

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --accept-package-agreements --accept-source-agreements --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

If the installer returns **1602**, it usually means the UAC prompt was declined or the session was not elevated—retry from an **Administrator** PowerShell and approve UAC.

**Option B — manual:** install [Build Tools for Visual Studio 2022](https://visualstudio.microsoft.com/visual-cpp-build-tools/) and select **Desktop development with C++** (or at least **MSVC** + **Windows SDK**).

**Rust:** `winget install --id Rustlang.Rustup -e --accept-package-agreements --accept-source-agreements` (or [rustup.rs](https://rustup.rs/)). After install, confirm `cargo --version` and that `%USERPROFILE%\.cargo\bin` is on your `PATH` (new terminal).

### Linux (including WSL2)

Use this when you build **inside Ubuntu/Debian on WSL** (you get a **Linux** `.deb` / `.AppImage`, not a Windows `.msi`).

1. **Prefer the Linux filesystem** for the clone (e.g. `~/src/SDM_Modern`), not ` /mnt/c/...` — much faster I/O for `npm` and `cargo`.

2. **System packages** (Tauri v1 + WebView; Ubuntu/Debian). **WebKit dev package name depends on Ubuntu release:**

   **Ubuntu 24.04 LTS (Noble) and Debian 13+** — `libwebkit2gtk-4.0-dev` was removed from the archive; use **4.1**:

   ```bash
   sudo apt update
   sudo apt install -y \
     build-essential curl wget file pkg-config \
     libssl-dev libgtk-3-dev libwebkit2gtk-4.1-dev \
     libayatana-appindicator3-dev librsvg2-dev
   ```

   **Ubuntu 22.04 LTS (Jammy) and older** — still ship the 4.0 package:

   ```bash
   sudo apt install -y \
     build-essential curl wget file pkg-config \
     libssl-dev libgtk-3-dev libwebkit2gtk-4.0-dev \
     libayatana-appindicator3-dev librsvg2-dev
   ```

   Tauri 1.x officially documents 4.0; on Noble, **4.1** is the installable package and is what most teams use for builds on 24.04. If linking still fails, see [Tauri issue #9662](https://github.com/tauri-apps/tauri/issues/9662) (Ubuntu 24 / WebKit) or build inside a 22.04 container/VM.

   Other distros: [Tauri v1 — Linux prerequisites](https://v1.tauri.app/v1/guides/getting-started/prerequisites).

   **Fedora** (from upstream docs; WebKit + toolchain):

   ```bash
   sudo dnf check-update
   sudo dnf install webkit2gtk3-devel.x86_64 openssl-devel curl wget libappindicator-gtk3 librsvg2-devel
   sudo dnf group install "C Development Tools and Libraries"
   ```

   **Arch / Manjaro**:

   ```bash
   sudo pacman -Syu
   sudo pacman -S --needed webkit2gtk base-devel curl wget openssl libappindicator-gtk3 librsvg libvips
   ```

3. **Rust** (if not already):

   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
   source "$HOME/.cargo/env"
   ```

4. **Python venv** (avoids **PEP 668** / `externally-managed-environment` on Ubuntu 24+):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -U pip setuptools wheel
   python -m pip install -r backend/requirements.txt -r backend/requirements-build.txt
   ```

5. **Node** — match `.nvmrc` (e.g. Node 20) via [nvm](https://github.com/nvm-sh/nvm) or NodeSource; then from repo root (venv still activated):

   ```bash
   npm ci
   npm run tauri build
   ```

   `beforeBuildCommand` already runs `npm run build` and `npm run sidecar:prepare`, so the Vite bundle and **Linux** PyInstaller sidecar (`sdm-api-x86_64-unknown-linux-gnu`, etc.) are produced during the Tauri build.

6. **Artifacts:** `src-tauri/target/release/bundle/` (e.g. `.deb`, `.AppImage`).

**WSL notes**

- **`tauri dev`:** needs a display; use **WSLg** (Windows 11) or an X server, or rely on **web-only** dev: `npm run dev` + (with `.venv` activated) `python backend/main.py` in two terminals (no Tauri window).
- **Port 8000:** if something in WSL already uses it, stop it or adjust your run configuration.
- **Ship to Windows users:** a Linux build does **not** replace a **Windows** `.msi`; build on Windows (or CI `windows-latest`) for that.
- **PyInstaller suddenly shows `Platform: Windows-...` while you are in a WSL shell:** your `npm` / `node` / `cargo` run is using the **Windows** toolchain (PATH interop or you launched the build from **PowerShell**, not Ubuntu). A real **Linux** sidecar log must show a Linux platform and write `sdm-api-x86_64-unknown-linux-gnu` (no `.exe`). Fix: install **Node + Rust inside WSL** (e.g. `nvm`, `rustup` in Ubuntu), `which node` must be under `/usr` or `$HOME`, not `/mnt/c/Program Files/...`; clone under `~/` if possible. With `.venv` activated, `npm run sidecar:prepare` uses that venv’s Python automatically; you can also set **`PYTHON=/full/path/to/.venv/bin/python3`**.

## Build the sidecar (PyInstaller)

From repository root:

```bash
npm run sidecar:prepare
```

This writes `src-tauri/binaries/sdm-api-<host-triple>[.exe]` (name must match the machine you build on).  
Repeat on **each** OS you ship (Windows build → Windows triple, macOS → Apple triple, etc.).

## Build the desktop installer

```bash
npm run tauri build
```

`tauri.conf.json` runs `npm run build && npm run sidecar:prepare` before the Rust bundle, so the sidecar is rebuilt when you package.

Outputs appear under `src-tauri/target/release/bundle/` (e.g. `.msi`, `.dmg`, `.AppImage` depending on OS).

## Development (`tauri dev`)

If no bundled sidecar sits next to the debug executable, the app **falls back** to:

`python backend/main.py` (or `python3` on Unix) with `backend/` as the working directory.

Start the Vite dev server as usual; ensure Python is on `PATH`.

## macOS (Apple Silicon or Intel)

Build **on a Mac** to produce a **Darwin** sidecar (`sdm-api-aarch64-apple-darwin` or `sdm-api-x86_64-apple-darwin`) and macOS bundles (e.g. **`.dmg`**, **`.app`** under `src-tauri/target/release/bundle/macos/`). Same repo steps as Linux: **venv**, `python -m pip install …`, `npm ci`, `npm run tauri build`.

### Prerequisites (system)

- **Xcode Command Line Tools** (compiler + SDK): `xcode-select --install`
- **Rust** (macOS target is usually installed by default with `rustup`; add the other arch if needed, e.g. `rustup target add x86_64-apple-darwin` on Apple Silicon for Intel builds).
- Official checklist: [Tauri v1 — macOS prerequisites](https://v1.tauri.app/v1/guides/getting-started/prerequisites) (same page as Linux; scroll to **macOS**).

### Code signing & notarization (distribution)

Apple’s **Gatekeeper** expects signed and **notarized** apps for smooth installs outside the Mac App Store. Summary (details and env vars are in the official guide):

- **Apple Developer Program** membership and a **Developer ID Application** certificate in Keychain (create CSR on the Mac, then create the cert in [Certificates, IDs & Profiles](https://developer.apple.com/account/resources/certificates/list)).
- Tauri **v1** uses **environment variables** so `tauri build` can sign and notarize in one go, for example:
  - **`APPLE_SIGNING_IDENTITY`** — name of the signing certificate in Keychain.
  - **Notarization (Apple ID):** `APPLE_ID`, `APPLE_PASSWORD` (app-specific password), `APPLE_TEAM_ID`.
  - **Or** **App Store Connect API key:** `APPLE_API_ISSUER`, `APPLE_API_KEY`, `APPLE_API_KEY_PATH`.

Full step-by-step and CI notes: **[Code signing macOS applications (Tauri v1)](https://v1.tauri.app/v1/guides/distribution/sign-macos/)**.

### Unsigned / local builds

Test builds without signing may still run after **Right-click the app → Open** the first time (or System Settings → Privacy & Security). That is **not** sufficient for arbitrary end users downloading your `.dmg`; plan signing + notarization for real releases.

### If notarization fails

Often **accept updated agreements** in [Apple Developer](https://developer.apple.com/account) (membership / agreements). See also community threads linked from [Tauri issue #7665](https://github.com/tauri-apps/tauri/issues/7665) (upload / `xcrun` errors).

## Troubleshooting

- **`cargo` / `rustc` not found**: install Rust (see Windows section above or [rustup.rs](https://rustup.rs/)), then restart the terminal so `PATH` picks up `%USERPROFILE%\.cargo\bin`.
- **`linker 'link.exe' not found` (Windows)**: install **Visual Studio Build Tools** with the **C++** / **VCTools** workload (see Windows section above).
- **“Bundled API not found”** in a release build: run `npm run sidecar:prepare` and confirm `src-tauri/binaries/sdm-api-<triple>` exists before `tauri build`.
- **API did not become ready**: port `8000` in use, or PyInstaller binary crashed — run the sidecar from a terminal to see Python errors.
- **PyInstaller `PermissionError` / `Access is denied` on `backend/dist/sdm-api.exe` (Windows)**: another process has the file open (often a running **sdm-api.exe** from a previous `tauri dev` / desktop run). Quit the app or end **sdm-api.exe** in Task Manager, then run `npm run sidecar:prepare` again. The prepare script also attempts `taskkill` and retries deleting the old exe before building.
- **`externally-managed-environment` even with `(.venv)` in the prompt**: the `pip` you ran is still the **system** `pip` (PEP 668). Run `command -v pip` — it must be `.../SDM_Modern/.venv/bin/pip`. Prefer **`python -m pip ...`** after `source .venv/bin/activate`, or **`.venv/bin/python -m pip ...`** explicitly. In bash, try `hash -r` if commands were cached. Recreate if needed: `rm -rf .venv && python3 -m venv .venv && source .venv/bin/activate && python -m pip install -U pip setuptools wheel`. On Ubuntu, install **`sudo apt install python3-venv python3-full`** if the venv has no usable pip.
