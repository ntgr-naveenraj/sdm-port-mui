# SDM Manager - React + Flask Implementation

A modern web-based replacement for the original Python/Tkinter SDM (Service Delivery Module) Manager.

## Developer documentation

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — setup, local run, checks before a PR
- **[docs/RELEASE.md](docs/RELEASE.md)** — versioning, builds, distributing installers
- **[docs/PACKAGING.md](docs/PACKAGING.md)** — Tauri + PyInstaller sidecar
- **[CHANGELOG.md](CHANGELOG.md)** — release notes
- **Tool versions:** `.nvmrc` (Node), `.python-version` (Python)
- **Optional env template:** [.env.example](.env.example)

## Quick Start

### Backend
```bash
cd backend
python main.py
# Runs on http://127.0.0.1:8000
```

### Frontend
```bash
npm run dev
# Opens on http://localhost:5173
```

### Desktop app (Tauri + bundled API)

See [docs/PACKAGING.md](docs/PACKAGING.md). Summary:

1. Create and use a **Python venv** (required on Ubuntu 24+ / PEP 668), then:  
   `pip install -r backend/requirements.txt -r backend/requirements-build.txt`
2. `npm run sidecar:prepare` — builds `sdm-api` with PyInstaller and copies it to `src-tauri/binaries/`
3. `npm run tauri build` — produces `.msi` / `.dmg` / etc.; the installer starts the API on port 8000 automatically.

`tauri dev` still uses `python backend/main.py` when no sidecar sits next to the debug executable.

## Features

### Device Management
- Browse all devices from Insight Cloud
- Select multiple devices for bulk operations
- View device status and SDM configuration
- Filter by organization and location

### Single Device Operations
- Check SDM status
- Enable/Disable SDM
- Share diagnostics
- Execute SSH commands
- Transfer files (upload/download)

### Bulk Operations
- Enable SDM on multiple devices
- Disable SDM on multiple devices
- Share diagnostics with email recipients
- Export device list to CSV

### Batch Operations
- Upload CSV with device list
- Execute commands on multiple devices (parallel)
- Transfer files on multiple devices (parallel)
- View detailed operation results

## Architecture

- **Backend:** Python Flask with real API integration
- **Frontend:** React + TypeScript with Material-UI
- **Authentication:** Insight Cloud credentials
- **State Management:** Zustand with persistence
- **SSH:** Subprocess-based SSH/SCP for device operations
- **Batch Processing:** Threading for parallel operations

## File Structure

The API is a **single Flask app** (`backend/main.py`). Insight URLs and keys live in `services/auth_service.py` (`Config.ENVIRONMENTS`).

```
backend/
├── main.py                  # Flask app — all HTTP routes
├── sdm-api.spec             # PyInstaller spec for Tauri sidecar
├── services/
│   ├── auth_service.py      # Insight auth + environment config
│   ├── api_service.py       # Organizations, locations, devices
│   ├── sdm_service.py       # SDM enable/disable/status
│   ├── ssh_service.py       # SSH / SCP for one device
│   ├── batch_ssh.py         # Parallel SSH/SCP from CSV
│   └── csv_parser.py        # CSV parsing for batch flows
└── requirements.txt

src/
├── pages/
│   ├── AuthPage.tsx         # Login (email/password + session tokens)
│   └── DashboardPage.tsx    # Device management + hierarchy + bulk actions
├── components/
│   ├── DeviceDataTable.tsx  # Device grid, filters, pagination
│   └── FileTransferBatch.tsx # File transfer tab (batch-oriented UI)
├── services/
│   └── api.ts               # Axios client → Flask API
├── store/
│   └── authStore.ts
└── utils/
    └── constants.ts
```

## Dependencies

### Backend
- flask, flask-cors, werkzeug
- requests, certifi
- pexpect (SSH)

### Frontend
- react, react-dom
- @mui/material, @mui/icons-material
- Custom device table (`DeviceDataTable`): resizable columns, pagination
- axios, zustand, typescript
