"""一键构建：先 npm run build 产出 frontend/dist，再 PyInstaller 打 onedir 包。

产物：dist/down_note/（down_note.exe + _internal/）+ dist/down_note-v*.0-setup.exe（装了
Inno Setup 时顺带产出安装包）。绿色版整目录打 zip、安装包单文件，两者都可作为发布物。
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
APP_DIST = ROOT / "dist" / "down_note"
ISCC = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"


def run(step: str, cmd: list[str], cwd: Path | None = None) -> None:
    print(f"[构建] {step}：{' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> None:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("未找到 npm：打包前需要 Node 构建一次前端")
    run("前端构建", [npm, "run", "build"], cwd=FRONTEND)
    run("PyInstaller", [sys.executable, "-m", "PyInstaller", "scripts/down_note.spec",
                        "--noconfirm", "--clean"], cwd=ROOT)
    if not (APP_DIST / "down_note.exe").is_file():
        raise SystemExit(f"构建产物缺失：{APP_DIST}")
    shutil.copy(ROOT / "scripts" / "使用说明.txt", APP_DIST / "使用说明.txt")
    if ISCC.is_file():
        run("安装包", [str(ISCC), "scripts/down_note.iss"], cwd=ROOT)
    else:
        print("[跳过] 未找到 Inno Setup（ISCC.exe），只产出绿色版")
    print(f"[完成] {APP_DIST}（绿色版整目录打 zip 即为发布物）")


if __name__ == "__main__":
    main()
