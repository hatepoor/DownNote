// 低落日记 · 应用图标：裁切 / 编码 / 合成 .ico
//
// 不要直接跑本文件——请跑 `bash 打包.sh`，它负责先用 Edge 把 SVG 栅格化成 256 窗口截图，
// 再把截图目录传进来。（本机 Node 子进程被运行环境拦截，无法在脚本内直接调起浏览器。）
//
// 本文件做三件事：
//   1. 从 256×256 截图左上角按目标尺寸精确裁切——不重采样，得到的正是浏览器在 N 个 CSS 像素下的原始栅格化结果；
//   2. 重新编码成 PNG；
//   3. 七档合成单一 .ico（PNG 压缩条目，Windows Vista 及以上支持）。
// PNG 编解码与 ICO 组装均为纯 Node 实现，只用内置 zlib，不引任何依赖。

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import zlib from 'node:zlib';

/* ---------- PNG 编解码 ---------- */

const crcTable = (() => {
  const t = new Int32Array(256);
  for(let n = 0; n < 256; n++){
    let c = n;
    for(let k = 0; k < 8; k++){ c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1); }
    t[n] = c;
  }
  return t;
})();

function crc32(buf){
  let c = -1;
  for(let i = 0; i < buf.length; i++){ c = crcTable[(c ^ buf[i]) & 0xff] ^ (c >>> 8); }
  return (c ^ -1) >>> 0;
}

function pngChunk(type, data){
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length, 0);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(body), 0);
  return Buffer.concat([len, body, crc]);
}

function encodePng(width, height, rgba){
  const stride = width * 4;
  const raw = Buffer.alloc((stride + 1) * height);
  for(let y = 0; y < height; y++){
    raw[y * (stride + 1)] = 0;
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', zlib.deflateSync(raw, { level: 9 })),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

function decodePng(file){
  const b = readFileSync(file);
  let p = 8, w = 0, h = 0, ct = 6;
  const idat = [];
  while(p < b.length){
    const len = b.readUInt32BE(p);
    const type = b.toString('ascii', p + 4, p + 8);
    const data = b.subarray(p + 8, p + 8 + len);
    if(type === 'IHDR'){ w = data.readUInt32BE(0); h = data.readUInt32BE(4); ct = data[9]; }
    else if(type === 'IDAT'){ idat.push(data); }
    else if(type === 'IEND'){ break; }
    p += 12 + len;
  }
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const ch = ct === 6 ? 4 : ct === 2 ? 3 : 1;
  const stride = w * ch;
  const out = Buffer.alloc(h * stride);
  for(let y = 0; y < h; y++){
    const filter = raw[y * (stride + 1)];
    const line = raw.subarray(y * (stride + 1) + 1, y * (stride + 1) + 1 + stride);
    const prev = y > 0 ? out.subarray((y - 1) * stride, y * stride) : Buffer.alloc(stride);
    for(let i = 0; i < stride; i++){
      const a = i >= ch ? out[y * stride + i - ch] : 0;
      const bb = prev[i];
      const c = i >= ch ? prev[i - ch] : 0;
      const x = line[i];
      let v;
      if(filter === 0){ v = x; }
      else if(filter === 1){ v = x + a; }
      else if(filter === 2){ v = x + bb; }
      else if(filter === 3){ v = x + ((a + bb) >> 1); }
      else {
        const pa = Math.abs(bb - c), pb = Math.abs(a - c), pc = Math.abs(a + bb - 2 * c);
        v = x + (pa <= pb && pa <= pc ? a : pb <= pc ? bb : c);
      }
      out[y * stride + i] = v & 255;
    }
  }
  const rgba = Buffer.alloc(w * h * 4);
  for(let i = 0, n = w * h; i < n; i++){
    const isGray = ch === 1;
    rgba[i * 4 + 0] = out[i * ch];
    rgba[i * 4 + 1] = isGray ? out[i * ch] : out[i * ch + 1];
    rgba[i * 4 + 2] = isGray ? out[i * ch] : out[i * ch + 2];
    rgba[i * 4 + 3] = ch === 4 ? out[i * ch + 3] : 255;
  }
  return { w, h, rgba };
}

function cropTopLeft(src, size){
  const out = Buffer.alloc(size * size * 4);
  for(let y = 0; y < size; y++){
    src.rgba.copy(out, y * size * 4, y * src.w * 4, y * src.w * 4 + size * 4);
  }
  return out;
}

/* ---------- ICO 组装 ---------- */

function buildIco(entries, outPath){
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(entries.length, 4);
  const dir = Buffer.alloc(16 * entries.length);
  let offset = 6 + 16 * entries.length;
  entries.forEach((e, i) => {
    const b = i * 16;
    dir.writeUInt8(e.size >= 256 ? 0 : e.size, b + 0);
    dir.writeUInt8(e.size >= 256 ? 0 : e.size, b + 1);
    dir.writeUInt8(0, b + 2);
    dir.writeUInt8(0, b + 3);
    dir.writeUInt16LE(1, b + 4);
    dir.writeUInt16LE(32, b + 6);
    dir.writeUInt32LE(e.data.length, b + 8);
    dir.writeUInt32LE(offset, b + 12);
    offset += e.data.length;
  });
  writeFileSync(outPath, Buffer.concat([header, dir, ...entries.map(e => e.data)]));
}

/* ---------- 主流程 ---------- */

const here = dirname(fileURLToPath(import.meta.url));
const renderDir = process.argv[2];
if(!renderDir){
  console.error('用法：node 打包.mjs <栅格化截图目录>　（请直接跑 bash 打包.sh）');
  process.exit(1);
}

const outDir = join(here, 'png');
const sizes = [16, 24, 32, 48, 64, 128, 256];

mkdirSync(outDir, { recursive: true });

const entries = [];
for(const size of sizes){
  const shot = join(renderDir, `shot-${size}.png`);
  if(!existsSync(shot)){
    console.error(`缺少栅格化截图：${shot}`); process.exit(1);
  }
  const png = encodePng(size, size, cropTopLeft(decodePng(shot), size));
  writeFileSync(join(outDir, `icon-${size}.png`), png);
  entries.push({ size, data: png });
}
buildIco(entries, join(here, 'icon.ico'));
console.log(`icon.ico 已生成（${sizes.join(' / ')}）`);

/* ---------- 生成自包含预览页 ---------- */
// 模板里引用 png/xxx.png，这里全部内联成 data URI——
// 预览页常被单独拷走或经临时服务打开，相对路径会 404。

const templatePath = join(here, '图标预览.模板.html');
if(existsSync(templatePath)){
  const tpl = readFileSync(templatePath, 'utf8');
  const preview = tpl.replace(/src="(png\/[^"]+)"/g, (whole, rel) => {
    const file = join(here, rel);
    if(!existsSync(file)){ return whole; }
    return 'src="data:image/png;base64,' + readFileSync(file).toString('base64') + '"';
  });
  writeFileSync(join(here, '图标预览.html'), preview, 'utf8');
  console.log('图标预览.html 已生成（图片已内联，单文件可直接打开）');
}
