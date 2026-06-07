# Contributing to SDM Manager (SDM_Modern)

## Prerequisites

| Tool | Version | Notes |
|------|---------|--------|
| **Node.js** | See `.nvmrc` (LTS 20.x) | `nvm use` or install matching Node |
| **npm** | Comes with Node | Use `npm ci` in CI; `npm install` locally |
| **Python** | See `.python-version` (3.11) | 3.10+ usually works; 3.11 is the reference |
| **Rust** | stable | Required only for **Tauri** desktop builds |
| **pip** | — | For backend and PyInstaller (packaging) |

Optional: **Visual Studio Build Tools (C++)** on Windows when running `cargo` / `tauri build` — see [docs/PACKAGING.md](docs/PACKAGING.md).

## Local development (web UI + Flask API)

From the **repository root** (`SDM_Modern/`):

1. **Python virtual environment** (use on Ubuntu 24+ / PEP 668; recommended everywhere)

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   python -m pip install -U pip setuptools wheel
   python -m pip install -r backend/requirements.txt
   ```

   For **desktop packaging** (PyInstaller), also:

   ```bash
   python -m pip install -r backend/requirements-build.txt
   ```

   Use **`python -m pip`** (not bare `pip`) so Ubuntu never runs `/usr/bin/pip3` by mistake. Verify: `command -v python` → `.../SDM_Modern/.venv/bin/python`.

2. **Install frontend dependencies**

   ```bash
   npm install
   ```

3. **Run the API** (terminal 1, with `.venv` still activated so Flask sees installed packages)

   ```bash
   cd backend
   python main.py
   ```

   API listens on `http://127.0.0.1:8000` by default.

4. **Run the Vite dev server** (terminal 2, from repo root)

   ```bash
   npm run dev
   ```

   Open the URL shown (typically `http://localhost:5173`). The frontend targets the API URL in `src/utils/constants.ts`.

## Checks before opening a PR

```bash
npm run build
```

Backend smoke check (syntax):

```bash
python -m compileall backend -q
```

## Desktop (Tauri) builds

See [docs/PACKAGING.md](docs/PACKAGING.md) for sidecar + installer steps.

## Releases

See [docs/RELEASE.md](docs/RELEASE.md).

## Configuration

- **Insight environments / API keys:** `backend/services/auth_service.py` (`Config.ENVIRONMENTS`). Do not commit secrets; follow your team’s process for deployment config.
- **`.env.example`:** Documents optional env usage; see file header.
