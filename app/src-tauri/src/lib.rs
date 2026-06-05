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
        let (exe, args) = python_command()?;
        eprintln!("[sidecar] spawning {:?} {:?}", exe, args);
        let mut child = Command::new(&exe)
            .args(&args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .with_context(|| format!("spawning sidecar: {:?} {:?}", exe, args))?;
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

/// Locate the sidecar process to spawn.
///
/// Preferred path: a single-file PyInstaller-built executable shipped
/// next to the app (Tauri "sidecar" pattern). Fallback for development:
/// run sidecar/main.py with the project's Python interpreter.
///
/// Returns (program, args_to_pass_before_user_input).
fn python_command() -> Result<(PathBuf, Vec<PathBuf>)> {
    // In dev (debug builds) always run the live source so Python changes take
    // effect without rebuilding the PyInstaller sidecar. (The old code always
    // preferred the bundled exe, so `tauri dev` ran a stale build.) In release,
    // prefer the bundled exe so lab machines need no Python install.
    if cfg!(debug_assertions) {
        if let Some(dev) = dev_sidecar() {
            eprintln!("[sidecar] dev mode: {:?}", dev);
            return Ok(dev);
        }
    }
    if let Some(bundled) = bundled_sidecar_path() {
        if bundled.exists() {
            return Ok((bundled, vec![]));
        }
    }
    dev_sidecar().ok_or_else(|| anyhow!(
        "no sidecar found: build it (tools/build_sidecar.py) or set up the .venv"
    ))
}

/// Dev sidecar: run sidecar/main.py with the project's Python interpreter.
fn dev_sidecar() -> Option<(PathBuf, Vec<PathBuf>)> {
    let script = repo_root().join("sidecar").join("main.py");
    if !script.exists() {
        return None;
    }
    let exe = std::env::var_os("HOLOGRAPHY_PYTHON")
        .map(PathBuf::from)
        .or_else(|| {
            let venv = repo_root().join(".venv").join("Scripts").join("python.exe");
            if venv.exists() { Some(venv) } else { None }
        })
        .unwrap_or_else(|| PathBuf::from("python"));
    Some((exe, vec![script]))
}

/// Where the PyInstaller-built sidecar lives. Tauri bundles sidecar
/// binaries into the same directory as the main exe at install time.
fn bundled_sidecar_path() -> Option<PathBuf> {
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    let suffix = if cfg!(target_os = "windows") { ".exe" } else { "" };
    let candidates = [
        exe_dir.join(format!("holography-sidecar{}", suffix)),
        // Tauri 2 also strips the triple in some packaging modes
        exe_dir.join(format!("binaries/holography-sidecar{}", suffix)),
    ];
    candidates.into_iter().find(|p| p.exists())
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
    use tauri::menu::{MenuBuilder, MenuItemBuilder, PredefinedMenuItem, SubmenuBuilder};
    use tauri::{Emitter, Manager};

    tauri::Builder::default()
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // ── Native backdrop ──────────────────────────────────────
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

            // ── Menu bar (visible on macOS; on Windows the bar is
            //     hidden by the custom chrome but accelerators still fire) ─
            let about = PredefinedMenuItem::about(app.handle(), None, None)?;
            let quit  = PredefinedMenuItem::quit(app.handle(), None)?;
            let mini  = PredefinedMenuItem::minimize(app.handle(), None)?;
            let zoom  = PredefinedMenuItem::maximize(app.handle(), None)?;

            let prefs = MenuItemBuilder::with_id("menu_prefs", "Preferences…")
                .accelerator("CmdOrCtrl+,").build(app)?;
            let open_data = MenuItemBuilder::with_id("menu_open_data", "Open Data Folder…")
                .accelerator("CmdOrCtrl+O").build(app)?;
            let connect = MenuItemBuilder::with_id("menu_connect", "Connect Hardware")
                .accelerator("CmdOrCtrl+K").build(app)?;
            let disconnect = MenuItemBuilder::with_id("menu_disconnect", "Disconnect Hardware")
                .accelerator("CmdOrCtrl+Shift+K").build(app)?;
            let theme = MenuItemBuilder::with_id("menu_theme", "Toggle Theme")
                .accelerator("CmdOrCtrl+T").build(app)?;
            let start = MenuItemBuilder::with_id("menu_exp_start", "Start Experiment")
                .accelerator("CmdOrCtrl+R").build(app)?;
            let stop = MenuItemBuilder::with_id("menu_exp_stop", "Stop Experiment")
                .accelerator("CmdOrCtrl+.").build(app)?;

            // Tab nav (Cmd/Ctrl+1..6)
            let tab_items: Vec<_> = [
                ("menu_tab_run",          "Run Experiment", "CmdOrCtrl+1"),
                ("menu_tab_laser",        "Laser",          "CmdOrCtrl+2"),
                ("menu_tab_switch",       "Switch",         "CmdOrCtrl+3"),
                ("menu_tab_polarization", "Polarization",   "CmdOrCtrl+4"),
                ("menu_tab_config",       "Configuration",  "CmdOrCtrl+5"),
                ("menu_tab_results",      "Results",        "CmdOrCtrl+6"),
            ].iter().map(|(id, label, accel)| {
                MenuItemBuilder::with_id(*id, *label).accelerator(*accel).build(app).unwrap()
            }).collect();

            let app_menu = SubmenuBuilder::new(app, "Digital Holography")
                .item(&about).separator()
                .item(&prefs).separator()
                .item(&quit).build()?;
            let file_menu = SubmenuBuilder::new(app, "File")
                .item(&open_data).separator()
                .item(&connect).item(&disconnect).build()?;
            let exp_menu = SubmenuBuilder::new(app, "Experiment")
                .item(&start).item(&stop).build()?;
            let mut view_builder = SubmenuBuilder::new(app, "View");
            for it in &tab_items { view_builder = view_builder.item(it); }
            let view_menu = view_builder.separator().item(&theme).build()?;
            let win_menu = SubmenuBuilder::new(app, "Window")
                .item(&mini).item(&zoom).build()?;

            let menu = MenuBuilder::new(app)
                .item(&app_menu).item(&file_menu).item(&exp_menu)
                .item(&view_menu).item(&win_menu).build()?;
            app.set_menu(menu)?;

            // Route menu clicks to the frontend as a Tauri event
            app.on_menu_event(|app, event| {
                let id = event.id().as_ref();
                let _ = app.emit("menu", id);
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![sidecar_rpc])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
