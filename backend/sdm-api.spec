# PyInstaller spec: frozen Flask API for Tauri sidecar (run from backend/)
# Usage: cd backend && python -m PyInstaller --clean --noconfirm sdm-api.spec

import platform
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
HERE = Path(SPEC).resolve().parent

datas = list(collect_data_files("certifi"))
_ssh = HERE / "sshCommander"
if _ssh.is_dir():
    datas += [(str(_ssh / "sshcommand.py"), "sshCommander")]
    datas += [(str(_ssh / "__init__.py"), "sshCommander")]

hiddenimports = [
    "services.auth_service",
    "services.api_service",
    "services.batch_ssh",
    "services.csv_parser",
    "services.sdm_service",
    "services.ssh_service",
    "services.file_transfer_sshcommand",
    "requests",
    "certifi",
    "charset_normalizer",
    "idna",
    "urllib3",
    "pexpect",
    "pty",
    "flask",
    "flask_cors",
    "werkzeug",
    "werkzeug.routing",
    "jinja2",
    "markupsafe",
    "itsdangerous",
    "click",
    "blinker",
]

a = Analysis(
    ["main.py"],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Windowless on Windows so users don't see a console; keep console on Unix for logs in dev-like builds
console = platform.system() != "Windows"

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="sdm-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=console,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
