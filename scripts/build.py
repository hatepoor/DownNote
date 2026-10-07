"""一键构建：前端 → 后端 sidecar（PyInstaller）→ Tauri 打包（NSIS 中文安装包）。

产物：
- dist/DownNote_0.1.1_x64-setup.exe（安装版，发布用）
- src-tauri/target/release/down_note.exe（便携版裸 exe，仍需 resources 后端）
用法：uv run python scripts/build.py
对应开发文档：docx/v0.1.0/modules/10-打包发布.md
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SIDECAR_DIST = ROOT / "dist" / "down_note-backend"
SIDECAR_EXE = SIDECAR_DIST / "down_note-backend.exe"
RESOURCES_BACKEND = FRONTEND / "src-tauri" / "resources" / "backend"
BUNDLE_NSIS = FRONTEND / "src-tauri" / "target" / "release" / "bundle" / "nsis"


def run(step: str, cmd: list[str], cwd: Path | None = None) -> None:
    print(f"[构建] {step}：{' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> None:
    # Rust 不在系统 PATH 时补上（winget/默认安装位）
    cargoBin = Path.home() / ".cargo" / "bin"
    if cargoBin.is_dir() and not shutil.which("cargo"):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + str(cargoBin)
    if not shutil.which("cargo"):
        raise SystemExit("未找到 cargo：请先安装 Rust（rustup stable-msvc）")

    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("未找到 npm：需要 Node 环境")
    run("前端构建", [npm, "run", "build"], cwd=FRONTEND)

    run("后端 sidecar", [sys.executable, "-m", "PyInstaller", "scripts/backend.spec",
                         "--noconfirm", "--clean"], cwd=ROOT)
    if not SIDECAR_EXE.is_file():
        raise SystemExit(f"sidecar 产物缺失：{SIDECAR_EXE}")
    if RESOURCES_BACKEND.exists():
        shutil.rmtree(RESOURCES_BACKEND)
    shutil.copytree(SIDECAR_DIST, RESOURCES_BACKEND)

    run("Tauri 打包", [npm, "run", "tauri", "build"], cwd=FRONTEND)
    installers = sorted(BUNDLE_NSIS.glob("*.exe"))
    if not installers:
        raise SystemExit(f"NSIS 安装包未产出：{BUNDLE_NSIS}")
    newest = max(installers, key=lambda p: p.stat().st_mtime)
    shutil.copy(newest, ROOT / "dist" / newest.name)
    print(f"[完成] {ROOT / 'dist' / newest.name}（发布用安装包）")


if __name__ == "__main__":
    main()
