// Prevents additional console window on Windows in release builds
#![cfg_attr(all(not(debug_assertions), target_os = "windows"), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::Child;
use std::sync::Mutex;
use tauri::Manager;

/// Kills the Flask child when the Tauri app exits.
struct ApiProcess(Mutex<Option<Child>>);

impl Drop for ApiProcess {
    fn drop(&mut self) {
        if let Ok(mut g) = self.0.lock() {
            if let Some(mut c) = g.take() {
                let _ = c.kill();
                let _ = c.wait();
            }
        }
    }
}

fn sidecar_filename() -> String {
    let triple = env!("SDM_API_TRIPLE");
    if cfg!(target_os = "windows") {
        format!("sdm-api-{}.exe", triple)
    } else {
        format!("sdm-api-{}", triple)
    }
}

fn spawn_bundled_api() -> Result<Child, String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let dir = exe.parent().ok_or_else(|| "no parent dir for exe".to_string())?;
    let path = dir.join(sidecar_filename());
    if !path.is_file() {
        return Err(format!(
            "Bundled API not found (expected next to app): {}",
            path.display()
        ));
    }
    std::process::Command::new(&path)
        .spawn()
        .map_err(|e| format!("failed to spawn {}: {}", path.display(), e))
}

fn spawn_dev_python() -> Result<Child, String> {
    let backend = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("backend");
    let main_py = backend.join("main.py");
    if !main_py.is_file() {
        return Err(format!(
            "Dev: backend/main.py not found at {}",
            main_py.display()
        ));
    }
    let py = if cfg!(target_os = "windows") {
        "python"
    } else {
        "python3"
    };
    std::process::Command::new(py)
        .current_dir(&backend)
        .arg("main.py")
        .spawn()
        .map_err(|e| format!("dev spawn {} in {}: {}", py, backend.display(), e))
}

fn wait_for_api_ready(timeout_ms: u64) -> Result<(), String> {
    let step = 100u64;
    let mut waited = 0u64;
    while waited < timeout_ms {
        if std::net::TcpStream::connect("127.0.0.1:8000").is_ok() {
            return Ok(());
        }
        std::thread::sleep(std::time::Duration::from_millis(step));
        waited += step;
    }
    Err(format!(
        "API did not become ready on 127.0.0.1:8000 within {} ms",
        timeout_ms
    ))
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let mut child = match spawn_bundled_api() {
                Ok(c) => {
                    eprintln!("[sdm-manager] Started bundled API sidecar");
                    c
                }
                Err(e_bundle) => match spawn_dev_python() {
                    Ok(c) => {
                        eprintln!(
                            "[sdm-manager] Bundled API missing ({}), using dev Python backend",
                            e_bundle
                        );
                        c
                    }
                    Err(e_dev) => {
                        return Err(format!(
                            "Could not start API.\nBundled: {}\nDev Python: {}",
                            e_bundle, e_dev
                        )
                        .into());
                    }
                },
            };

            if let Err(e) = wait_for_api_ready(60_000) {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e.into());
            }

            app.manage(ApiProcess(Mutex::new(Some(child))));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
