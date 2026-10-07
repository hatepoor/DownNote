// 低落日记桌面壳：拉起 Python 后端 sidecar，就绪后显示窗口；退出时回收后端。
// 后端跑在壳分配的随机空闲端口上（DOWN_NOTE_PORT），前端经 invoke('backend_port') 读取。
// 对应开发文档：docx/v0.1.0/modules/10-打包发布.md（Tauri 迁移）

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::{TcpListener, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Emitter, Manager};

/// 后端进程句柄（退出时回收）
struct Backend(Mutex<Option<Child>>);

/// 后端 API 端口（None = 尚未就绪）
struct BackendPort(Mutex<Option<u16>>);

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .expect("绑定空闲端口失败")
        .local_addr()
        .expect("读取端口失败")
        .port()
}

fn spawn_backend(app: &tauri::AppHandle, port: u16) -> Result<Child, String> {
    let port_env = port.to_string();
    if cfg!(debug_assertions) {
        // 开发：直接用 uv 跑仓库里的后端（cargo 进程在 frontend/src-tauri，仓库根在上两级）
        Command::new("uv")
            .args(["run", "python", "-m", "down_note.serve"])
            .env("DOWN_NOTE_PORT", &port_env)
            .current_dir("../../")
            .spawn()
            .map_err(|e| format!("拉起后端失败：{e}"))
    } else {
        let exe = app
            .path()
            .resource_dir()
            .map_err(|e| format!("资源目录不可用：{e}"))?
            .join("resources")
            .join("backend")
            .join("down_note-backend.exe");
        Command::new(&exe)
            .env("DOWN_NOTE_PORT", &port_env)
            .stdin(Stdio::null())
            .spawn()
            .map_err(|e| format!("拉起后端失败（{}）：{}", exe.display(), e))
    }
}

/// 端口能连上即视为服务就绪（uvicorn 绑定并开始接受连接）
fn wait_backend(port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

fn kill_backend(backend: &Backend) {
    if let Some(mut child) = backend.0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[tauri::command]
fn backend_port(state: tauri::State<BackendPort>) -> Option<u16> {
    *state.0.lock().unwrap()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // 双开：唤起已有窗口而不是再开一个
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .manage(Backend(Mutex::new(None)))
        .manage(BackendPort(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![backend_port])
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let port = free_port();
                match spawn_backend(&handle, port) {
                    Ok(child) => {
                        *handle.state::<Backend>().0.lock().unwrap() = Some(child);
                        if wait_backend(port, Duration::from_secs(30)) {
                            *handle.state::<BackendPort>().0.lock().unwrap() = Some(port);
                            if let Some(w) = handle.get_webview_window("main") {
                                let _ = w.emit("backend-ready", port);
                                let _ = w.show();
                                let _ = w.set_focus();
                            }
                        } else {
                            kill_backend(handle.state::<Backend>().inner());
                            if let Some(w) = handle.get_webview_window("main") {
                                let _ = w.show();
                                let _ = w.eval(
                                    "document.title='启动失败'; document.body.innerHTML='<p style=\"color:#edeae2;font-family:sans-serif;padding:24px\">后端启动超时，请重启应用。</p>'",
                                );
                            }
                        }
                    }
                    Err(e) => {
                        if let Some(w) = handle.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.eval(&format!(
                                "document.body.innerHTML='<p style=\"color:#edeae2;font-family:sans-serif;padding:24px\">{e}</p>'"
                            ));
                        }
                    }
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                kill_backend(window.app_handle().state::<Backend>().inner());
            }
        })
        .build(tauri::generate_context!())
        .expect("Tauri 应用构建失败")
        .run(|app, event| {
            // 兜底：任何退出路径都回收后端进程
            if let tauri::RunEvent::Exit = event {
                kill_backend(app.state::<Backend>().inner());
            }
        });
}
