// 低落日记桌面壳：拉起 Python 后端 sidecar，就绪后显示窗口；关窗收托盘，退出时回收后端。
// 后端跑在壳分配的随机空闲端口上（DOWN_NOTE_PORT），前端经 invoke('backend_port') 读取。
// 托盘：左键点图标开窗、右键出菜单；关窗只藏窗口不退进程——主动陪伴（v0.2.0）要靠
// 常驻进程，真正退出只走托盘菜单。开发态（debug 构建）托盘另带「测试通知」项，
// 打后端 /api/notify/test 验证"开口 → 通知 → 回到对应会话"整条链路（打包版不含）。
// 对应开发文档：docx/v0.2.0/modules/01-托盘常驻与系统通知.md

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::Write;
use std::net::{TcpListener, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::menu::{CheckMenuItem, MenuBuilder, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_notification::NotificationExt;

/// 后端进程句柄（退出时回收）
struct Backend(Mutex<Option<Child>>);

/// 后端 API 端口（None = 尚未就绪）
struct BackendPort(Mutex<Option<u16>>);

/// 关窗提示是否已弹过（每次运行只提示一次）
struct TrayHintShown(AtomicBool);

/// 是否正在退出（退出路径不再拦截关窗）
struct Quitting(AtomicBool);

/// 托盘是否建成（未建成时关窗退应用——避免"窗口藏起来又唤不回"）
struct TrayReady(AtomicBool);

/// 托盘菜单里的「开机自启」勾选项（切换后要回写勾选态）
struct AutostartItem(Mutex<Option<CheckMenuItem<tauri::Wry>>>);

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

/// 结束后端：连子进程树一起收。
///
/// dev 模式下后端是 `uv run python -m down_note.serve`——uv → venv python → 真正的
/// uvicorn 三层，只 kill 直接子进程（uv）会把 python 留在后台：端口占着、APScheduler
/// 还在跑（应用都关了它还会"主动开口"）。所以 Windows 走 `taskkill /T`；
/// 打包版是直接 spawn `down_note-backend.exe`，同样适用。
#[cfg(windows)]
fn kill_backend(backend: &Backend) {
    use std::os::windows::process::CommandExt;

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    if let Some(mut child) = backend.0.lock().unwrap().take() {
        let pid = child.id().to_string();
        let killed_tree = Command::new("taskkill")
            .args(["/PID", pid.as_str(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status()
            .map(|status| status.success())
            .unwrap_or(false);
        if !killed_tree {
            let _ = child.kill(); // 兜底：taskkill 不可用时退回杀直接子进程
        }
        let _ = child.wait();
    }
}

#[cfg(not(windows))]
fn kill_backend(backend: &Backend) {
    if let Some(mut child) = backend.0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// 显示并聚焦主窗口：托盘打开、单实例唤起、通知点击激活三处共用
fn show_main_window(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

/// 开发自测：向后端发一个最小 POST（手写请求，不为此加 HTTP 依赖）
fn post_backend(path: &str, port: u16) -> std::io::Result<()> {
    let body = "{}";
    let request = format!(
            "POST {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
            body.len(),
        );
    let mut stream = TcpStream::connect(("127.0.0.1", port))?;
    stream.write_all(request.as_bytes())
}

/// 后台线程里打一个自测 POST（不阻塞托盘菜单线程）
fn spawn_backend_post(path: &'static str, port: u16) {
    std::thread::spawn(move || {
        let _ = post_backend(path, port);
    });
}

/// 切换开机自启并回写勾选态
fn toggle_autostart(app: &tauri::AppHandle) {
    let autolaunch = app.autolaunch();
    let enabled = autolaunch.is_enabled().unwrap_or(false);
    let switched = if enabled { autolaunch.disable() } else { autolaunch.enable() };
    if switched.is_err() {
        return;
    }
    let next = autolaunch.is_enabled().unwrap_or(!enabled);
    let state = app.state::<AutostartItem>();
    let guard = state.0.lock().unwrap();
    if let Some(item) = guard.as_ref() {
        let _ = item.set_checked(next);
    }
}

/// 建托盘：图标 + 菜单（打开主界面 / 开机自启 /〔开发〕测试通知 + 试一次开口 / 退出）
fn setup_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let open_item = MenuItem::with_id(app, "open", "打开主界面", true, None::<&str>)?;
    let autostart_on = app.autolaunch().is_enabled().unwrap_or(false);
    let autostart_item = CheckMenuItem::with_id(
            app,
            "autostart",
            "开机自启",
            true,
            autostart_on,
            None::<&str>,
        )?;
    let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;

    let mut menu_builder = MenuBuilder::new(app)
        .item(&open_item)
        .separator()
        .item(&autostart_item);
    #[cfg(debug_assertions)]
    let test_item = MenuItem::with_id(app, "notify-test", "测试通知（开发）", true, None::<&str>)?;
    #[cfg(debug_assertions)]
    let care_item = MenuItem::with_id(app, "companion-test", "试一次开口（开发）", true, None::<&str>)?;
    #[cfg(debug_assertions)]
    {
        menu_builder = menu_builder.item(&test_item).item(&care_item);
    }
    let menu = menu_builder.separator().item(&quit_item).build()?;

    let state = app.state::<AutostartItem>();
    *state.0.lock().unwrap() = Some(autostart_item);

    let mut tray_builder = TrayIconBuilder::new()
        .menu(&menu)
        .show_menu_on_left_click(false) // 左键开窗、右键出菜单（Windows 托盘惯例）
        .tooltip("低落日记（右键可退出）")
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => show_main_window(app),
            "autostart" => toggle_autostart(app),
            #[cfg(debug_assertions)]
            "notify-test" => {
                let port = *app.state::<BackendPort>().0.lock().unwrap();
                if let Some(port) = port {
                    let _ = post_backend("/api/notify/test", port);
                }
            }
            #[cfg(debug_assertions)]
            "companion-test" => {
                // 立刻让主动陪伴开口一次（跳过等待，其余判定照常）——生成要调模型，放后台线程
                let port = *app.state::<BackendPort>().0.lock().unwrap();
                if let Some(port) = port {
                    spawn_backend_post("/api/companion/patrol", port);
                }
            }
            "quit" => {
                app.state::<Quitting>().0.store(true, Ordering::SeqCst);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon().cloned() {
        tray_builder = tray_builder.icon(icon);
    }
    tray_builder.build(app)?;
    Ok(())
}

#[tauri::command]
fn backend_port(state: tauri::State<BackendPort>) -> Option<u16> {
    *state.0.lock().unwrap()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // 双开 / 点击通知唤起：显示并聚焦已有窗口，不产生第二个进程
            show_main_window(app);
        }))
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, Some(vec!["--hidden"])))
        .manage(Backend(Mutex::new(None)))
        .manage(BackendPort(Mutex::new(None)))
        .manage(TrayHintShown(AtomicBool::new(false)))
        .manage(Quitting(AtomicBool::new(false)))
        .manage(TrayReady(AtomicBool::new(false)))
        .manage(AutostartItem(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![backend_port])
        .setup(|app| {
            // 托盘失败不致命：记录状态，关窗回退为"退出"，不让窗口藏到唤不回来
            if setup_tray(app.handle()).is_ok() {
                app.state::<TrayReady>().0.store(true, Ordering::SeqCst);
            }
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                // 开机自启（--hidden）：静默驻留托盘，不弹窗抢焦点
                let start_hidden = std::env::args().any(|arg| arg == "--hidden");
                let port = free_port();
                match spawn_backend(&handle, port) {
                    Ok(child) => {
                        *handle.state::<Backend>().0.lock().unwrap() = Some(child);
                        if wait_backend(port, Duration::from_secs(30)) {
                            *handle.state::<BackendPort>().0.lock().unwrap() = Some(port);
                            if let Some(w) = handle.get_webview_window("main") {
                                let _ = w.emit("backend-ready", port);
                                if !start_hidden {
                                    let _ = w.show();
                                    let _ = w.set_focus();
                                }
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
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                if app.state::<Quitting>().0.load(Ordering::SeqCst) {
                    return;
                }
                if !app.state::<TrayReady>().0.load(Ordering::SeqCst) {
                    return; // 没有托盘可回：照旧关窗即退出
                }
                // 关窗收托盘：藏起来不退进程；退出只走托盘菜单
                api.prevent_close();
                let _ = window.hide();
                // 首次关窗提示一次（每次运行一次）：它不是关了，是收起来了
                if !app.state::<TrayHintShown>().0.swap(true, Ordering::SeqCst) {
                    let _ = app
                        .notification()
                        .builder()
                        .title("低落日记")
                        .body("已收进托盘，还在后台；右键托盘图标可退出")
                        .show();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("Tauri 应用构建失败")
        .run(|app, event| {
            // 兜底：任何退出路径都回收后端进程（调度随进程一起结束）
            if let tauri::RunEvent::Exit = event {
                kill_backend(app.state::<Backend>().inner());
            }
        });
}
