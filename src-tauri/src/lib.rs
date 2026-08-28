use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};
use tauri::Manager;

/// FastAPI sidecar 子进程句柄，随应用退出时终止。
struct Sidecar(Child);

/// 拉起 backend/main.py 并等待 /api/health 就绪。
fn spawn_backend(app: &tauri::AppHandle) -> Result<(), String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resolve resource dir: {e}"))?;

    // 开发期：仓库内 venv 的 python；打包后：随包分发的 runtime
    let python = if cfg!(debug_assertions) {
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../backend/.venv/Scripts/python.exe")
    } else {
        resource_dir.join("runtime/python.exe")
    };

    let script = if cfg!(debug_assertions) {
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../backend/main.py")
    } else {
        resource_dir.join("backend/main.py")
    };

    let child = Command::new(&python)
        .arg(&script)
        .env("AGENT_ROOM_PORT", "8899")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("spawn backend ({:?}): {e}", python))?;
    app.manage(Sidecar(child));

    // 健康检查：最多等 15 秒
    let deadline = Instant::now() + Duration::from_secs(15);
    while Instant::now() < deadline {
        if let Ok(body) = reqwest_no_block() {
            if body.contains("\"ok\":true") {
                return Ok(());
            }
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    Err("backend health check timeout (127.0.0.1:8899/api/health)".into())
}

/// 用最小 TCP 连接探测健康端点（避免额外 HTTP 依赖）。
#[allow(dead_code)]
fn reqwest_no_block() -> Result<String, ()> {
    use std::io::{Read, Write};
    use std::net::TcpStream;
    let mut stream = TcpStream::connect("127.0.0.1:8899").map_err(|_| ())?;
    stream
        .write_all(b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:8899\r\nConnection: close\r\n\r\n")
        .map_err(|_| ())?;
    let mut buf = String::new();
    stream.read_to_string(&mut buf).map_err(|_| ())?;
    Ok(buf)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      spawn_backend(app.handle()).map_err(std::io::Error::other)?;
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
