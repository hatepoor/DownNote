#!/usr/bin/env bash
# 低落日记 · 应用图标：栅格化 + 打包 一键脚本
#
#   bash 打包.sh
#
# 为什么要拆成两半：本机 Node 子进程被运行环境拦截（spawnSync 返回 status=null），
# 脚本内无法直接调起 Edge。故栅格化交给 bash（可正常调起 msedge），
# 裁切/编码/合成 .ico 交给 打包.mjs（纯字节操作，不需要子进程）。
#
# 产物：png/icon-{16,24,32,48,64,128,256}.png、icon.ico、图标预览.html
# 中间件：$TEMP/icon-render/（可随时删）

set -euo pipefail
cd "$(dirname "$0")"

EDGE=""
for p in "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
         "/c/Program Files/Microsoft/Edge/Application/msedge.exe"; do
  [ -x "$p" ] && EDGE="$p" && break
done
if [ -z "$EDGE" ]; then
  echo "未找到 msedge.exe" >&2; exit 1
fi

RENDER="$(cygpath -u "$TEMP")/icon-render"
rm -rf "$RENDER"; mkdir -p "$RENDER"

SIZES="16 24 32 48 64 128 256"
WINDOW=256

# Edge 窗口有最小尺寸，16px 窗口出不了图：统一用 256 窗口渲染、SVG 贴左上角，之后按尺寸精确裁切。
# 另：Chromium 会把 --screenshot 路径里的反斜杠当转义字符，故一律用 cygpath -m 转成正斜杠。
for size in $SIZES; do
  if [ "$size" -le 24 ]; then
    master="icon-small.svg"
  else
    master="icon.svg"
  fi
  page="$RENDER/page-$size.html"
  {
    printf '<!doctype html><meta charset="utf-8"><style>'
    printf 'html,body{margin:0;padding:0;overflow:hidden;background:transparent}'
    printf 'svg{display:block;position:absolute;top:0;left:0;width:%spx;height:%spx}' "$size" "$size"
    printf '</style>'
    cat "$master"
  } > "$page"
  shot="$(cygpath -m "$RENDER")/shot-$size.png"
  pageUrl="file:///$(cygpath -m "$page")"
  # Edge 无头偶发静默失败，重试三次
  for attempt in 1 2 3; do
    # --disable-lcd-text 必须加：小尺寸母版用字体渲染，不禁用次像素抗锯齿会在字缘留彩色镶边
    # （实测 16px 下带彩边像素 116 个、最大色偏 90；禁用后为 0 个、1.0）
    "$EDGE" --headless=new --disable-gpu --disable-lcd-text --hide-scrollbars --force-device-scale-factor=1 \
      --default-background-color=00000000 \
      --window-size="$WINDOW,$WINDOW" --virtual-time-budget=3000 \
      --screenshot="$shot" "$pageUrl" >/dev/null 2>&1 || true
    [ -f "$RENDER/shot-$size.png" ] && break
    echo "  尺寸 $size 第 $attempt 次渲染失败，重试…" >&2
    sleep 2
  done
  if [ ! -f "$RENDER/shot-$size.png" ]; then
    echo "尺寸 $size 渲染三次仍失败，中止。" >&2
    echo "提示：Edge 无头进程会累积并导致后续渲染失败，先执行 taskkill //F //IM msedge.exe 再重跑。" >&2
    exit 1
  fi
done

echo "栅格化完成，开始裁切与合成 .ico ……"
node 打包.mjs "$(cygpath -m "$RENDER")"
