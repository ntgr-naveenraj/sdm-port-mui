/**
 * Build Flask backend with PyInstaller and copy to src-tauri/binaries/
 * using the name Tauri expects for externalBin: sdm-api-<rustc-host-triple>[.exe]
 *
 * Run from repo root: node scripts/sidecar-prepare.mjs
 */

import { execSync, spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, unlinkSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");
const backend = join(root, "backend");
const binDir = join(root, "src-tauri", "binaries");

function getRustcTriple() {
  try {
    const out = execSync("rustc -vV", {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    const line = out.split("\n").find((l) => l.startsWith("host: "));
    if (line) return line.replace("host: ", "").trim();
  } catch {
    /* rustc not on PATH */
  }
  if (process.env.TAURI_SIDECAR_TRIPLE?.trim()) {
    return process.env.TAURI_SIDECAR_TRIPLE.trim();
  }
  return inferTripleFromNode();
}

/** When rustc is unavailable; must match the host triple used by `tauri build` on this machine. */
function inferTripleFromNode() {
  const p = process.platform;
  const a = process.arch;
  if (p === "win32") {
    return a === "arm64" ? "aarch64-pc-windows-msvc" : "x86_64-pc-windows-msvc";
  }
  if (p === "darwin") {
    return a === "arm64" ? "aarch64-apple-darwin" : "x86_64-apple-darwin";
  }
  if (p === "linux") {
    return a === "arm64" ? "aarch64-unknown-linux-gnu" : "x86_64-unknown-linux-gnu";
  }
  throw new Error(`Unsupported platform for sidecar naming: ${p} ${a}`);
}

const triple = getRustcTriple();
const ext = process.platform === "win32" ? ".exe" : "";
const dest = join(binDir, `sdm-api-${triple}${ext}`);

mkdirSync(binDir, { recursive: true });

const builtExe = join(backend, "dist", `sdm-api${process.platform === "win32" ? ".exe" : ""}`);

/** Windows: PyInstaller must replace dist/sdm-api.exe — fails with EACCES if the sidecar is still running. */
function sleepMs(ms) {
  try {
    if (process.platform === "win32") {
      execSync(`powershell -NoProfile -Command "Start-Sleep -Milliseconds ${ms}"`, { stdio: "ignore" });
    } else {
      execSync(`sleep ${Math.max(1, Math.ceil(ms / 1000))}`, { stdio: "ignore" });
    }
  } catch {
    /* ignore */
  }
}

function unlockSidecarOutput() {
  if (process.platform === "win32") {
    try {
      execSync("taskkill /F /IM sdm-api.exe /T", { stdio: "ignore", shell: true });
      sleepMs(400);
    } catch {
      /* not running or access denied — continue */
    }
  }
  if (!existsSync(builtExe)) return;
  for (let i = 0; i < 8; i++) {
    try {
      unlinkSync(builtExe);
      return;
    } catch {
      sleepMs(350);
    }
  }
  console.error(
    [
      `Cannot remove locked file: ${builtExe}`,
      "Stop any running sdm-api.exe (SDM Manager, Task Manager) or terminals using it, then retry.",
      "If antivirus holds the file, exclude backend/dist or retry after a moment.",
    ].join("\n")
  );
  process.exit(1);
}

unlockSidecarOutput();

/** Prefer explicit PYTHON, then an active venv, so WSL/Linux builds do not accidentally pick Windows Python from PATH. */
function pythonForPyInstaller() {
  const fromEnv = process.env.PYTHON?.trim();
  if (fromEnv) return fromEnv;
  const ve = process.env.VIRTUAL_ENV?.trim();
  if (ve) {
    if (process.platform === "win32") {
      return join(ve, "Scripts", "python.exe");
    }
    return join(ve, "bin", "python");
  }
  return process.platform === "win32" ? "python" : "python3";
}

const py = pythonForPyInstaller();
const r = spawnSync(
  py,
  ["-m", "PyInstaller", "--clean", "--noconfirm", "sdm-api.spec"],
  { cwd: backend, stdio: "inherit", env: process.env }
);

if (r.status !== 0 && r.status !== null) {
  console.error("PyInstaller failed. Install build deps: pip install -r backend/requirements-build.txt");
  process.exit(r.status);
}

const built = builtExe;
if (!existsSync(built)) {
  console.error(`Expected PyInstaller output missing: ${built}`);
  process.exit(1);
}

copyFileSync(built, dest);
if (process.platform !== "win32") {
  spawnSync("chmod", ["+x", dest], { stdio: "inherit" });
}
console.log("Sidecar ready:", dest);
