use anyhow::{anyhow, Context, Result};
use once_cell::sync::OnceCell;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

/// One JSON-RPC-shaped request/response over the sidecar's stdio.
#[derive(Serialize)]
struct Request<'a> {
    id: u64,
    method: &'a str,
    params: Value,
}
#[derive(Deserialize)]
struct Response {
    id: u64,
    ok: bool,
    #[serde(default)]
    result: Value,
    #[serde(default)]
    error: String,
}

struct Sidecar {
    _child: Child,
    stdin:  ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: AtomicU64,
}

impl Sidecar {
    fn spawn() -> Result<Self> {
        let (exe, script) = python_command()?;
        eprintln!("[sidecar] spawning {:?} {:?}", exe, script);
        let mut child = Command::new(&exe)
            .arg(&script)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .with_context(|| format!("spawning Python sidecar: {:?} {:?}", exe, script))?;
        let stdin  = child.stdin.take().ok_or_else(|| anyhow!("no stdin"))?;
        let stdout = BufReader::new(child.stdout.take().ok_or_else(|| anyhow!("no stdout"))?);
        Ok(Self { _child: child, stdin, stdout, next_id: AtomicU64::new(1) })
    }

    fn call(&mut self, method: &str, params: Value) -> Result<Value> {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let req = Request { id, method, params };
        let mut line = serde_json::to_string(&req)?;
        line.push('\n');
        self.stdin.write_all(line.as_bytes()).context("writing to sidecar stdin")?;
        self.stdin.flush().context("flushing sidecar stdin")?;

        // Read responses until we find the one matching our id (in practice
        // the sidecar always answers in order, but the loop is defensive).
        let deadline = Instant::now() + Duration::from_secs(120);
        loop {
            if Instant::now() > deadline {
                return Err(anyhow!("sidecar response timeout for method '{}'", method));
            }
            let mut buf = String::new();
            let n = self.stdout.read_line(&mut buf).context("reading sidecar stdout")?;
            if n == 0 {
                return Err(anyhow!("sidecar closed stdout unexpectedly"));
            }
            let response: Response = match serde_json::from_str(buf.trim()) {
                Ok(r) => r,
                Err(_) => continue, // unparseable line — skip
            };
            if response.id != id { continue; }
            if response.ok { return Ok(response.result); }
            return Err(anyhow!("{}", response.error));
        }
    }
}

static SIDECAR: OnceCell<Arc<Mutex<Sidecar>>> = OnceCell::new();

fn sidecar() -> Result<Arc<Mutex<Sidecar>>> {
    SIDECAR
        .get_or_try_init(|| Sidecar::spawn().map(|s| Arc::new(Mutex::new(s))))
        .cloned()
}

/// Locate the Python interpreter and sidecar/main.py.
///
/// Search order:
///   1. HOLOGRAPHY_PYTHON  env var (full path to python.exe)
///   2. <repo>/.venv/Scripts/python.exe
///   3. "python" on PATH
fn python_command() -> Result<(PathBuf, PathBuf)> {
    let exe = std::env::var_os("HOLOGRAPHY_PYTHON")
        .map(PathBuf::from)
        .or_else(|| {
            let venv = repo_root().join(".venv").join("Scripts").join("python.exe");
            if venv.exists() { Some(venv) } else { None }
        })
        .unwrap_or_else(|| PathBuf::from("python"));
    let script = repo_root().join("sidecar").join("main.py");
    if !script.exists() {
        return Err(anyhow!("sidecar script missing at {:?}", script));
    }
    Ok((exe, script))
}

/// `<src-tauri>/../..` — i.e. the repo root where `sidecar/` and `hardware/` live.
fn repo_root() -> PathBuf {
    // CARGO_MANIFEST_DIR is <repo>/app/src-tauri
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
    manifest.parent().and_then(|p| p.parent())
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default())
}

#[tauri::command]
fn sidecar_rpc(method: String, params: Value) -> Result<Value, String> {
    let sc = sidecar().map_err(|e| e.to_string())?;
    let mut guard = sc.lock().map_err(|e| e.to_string())?;
    guard.call(&method, params).map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            use tauri::Manager;
            // Best-effort native backdrop. Win11 → Mica (with dark fallback);
            // macOS → window vibrancy; older Win10 → silently no-op.
            if let Some(win) = app.get_webview_window("main") {
                #[cfg(target_os = "windows")]
                {
                    let _ = window_vibrancy::apply_mica(&win, Some(true))
                        .or_else(|_| window_vibrancy::apply_acrylic(&win, None));
                }
                #[cfg(target_os = "macos")]
                {
                    let _ = window_vibrancy::apply_vibrancy(
                        &win,
                        window_vibrancy::NSVisualEffectMaterial::HudWindow,
                        None,
                        Some(8.0),
                    );
                }
                let _ = win;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![sidecar_rpc])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
