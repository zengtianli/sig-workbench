/* sig-core.js — 签名抠图算法核心（浏览器端）
 *
 * ⚠ SSOT 关系：本文件是 engine/sig_extract.py 的浏览器实现，
 *   两边算法必须一致（同一张图应给出同样的 Otsu 阈值与墨占比）。改一边必须改另一边，
 *   并跑 test-harness.html 对账（headless chrome --dump-dom，见同目录 verify.sh）。
 *
 * 生产页 web/index.html 与测试页 test-harness.html 都引用本文件 —— 测的就是跑的。
 *
 * ⚠ 全部代码包在 IIFE 里，只往全局导出 window.SigCore —— 不是风格洁癖：
 *   classic script 顶层的 `function extract` 会挂成全局属性，而消费方写
 *   `const {extract} = window.SigCore` 会创建同名全局词法绑定 → 重复声明
 *   SyntaxError → **消费方整个 script 在实例化阶段就不执行、函数一个都不 hoist**。
 *   2026-08-14 实测症状：页面正常渲染、控制台之外无任何迹象，但点击毫无反应。
 */
(function(){
'use strict';
/* ── 签名抠图算法（与 sig_extract.py 同一套；改一边记得改另一边）───────────── */

const MIN_INK = 0.003, MAX_INK = 0.45;
const INKS = {black:[0,0,0], blue:[26,58,143], darkblue:[12,35,92]};

/** 一维滑动窗极值（单调双端队列，O(n)）。mode: 'max' | 'min'
 *
 * ⚠ 队列长度必须按 inner（行长/列高）分配，不是按核宽 k —— tail 是单调增的写指针，
 *   不是环形。按 k+2 分配会让 Int32Array 越界写**静默丢弃**、越界读给 undefined，
 *   于是整个极值算成垃圾：2026-08-14 对账实测，同一张图 JS 墨占比 1.51% vs
 *   Python 15.91%（丢了 10 倍笔画），而页面照常渲染、无任何报错。
 */
function slide1d(src, w, h, k, horiz, mode){
  const out = new Float32Array(src.length), r = k >> 1;
  const outer = horiz ? h : w, inner = horiz ? w : h;
  const q = new Int32Array(inner + 1);
  const better = mode === 'max' ? (a, b) => a >= b : (a, b) => a <= b;
  const step = horiz ? 1 : w;
  for (let o = 0; o < outer; o++){
    const base = horiz ? o * w : o;
    let head = 0, tail = 0, j = 0;
    for (let i = 0; i < inner; i++){
      const hi = Math.min(inner - 1, i + r);       // 窗口右界，入队到这
      while (j <= hi){
        const v = src[base + j * step];
        while (tail > head && better(v, src[base + q[tail-1] * step])) tail--;
        q[tail++] = j; j++;
      }
      const lo = i - r;                             // 窗口左界，过期的出队
      while (q[head] < lo) head++;
      out[base + i * step] = src[base + q[head] * step];
    }
  }
  return out;
}

/** 分离式 box 均值（前缀和，O(n)） */
function boxBlur(src, w, h, k){
  const r = k >> 1, tmp = new Float32Array(src.length), out = new Float32Array(src.length);
  for (let y = 0; y < h; y++){
    let acc = 0; const row = y*w;
    for (let x = 0; x < Math.min(r, w); x++) acc += src[row+x];
    for (let x = 0; x < w; x++){
      const add = x + r, sub = x - r - 1;
      if (add < w) acc += src[row+add];
      if (sub >= 0) acc -= src[row+sub];
      const n = Math.min(x+r, w-1) - Math.max(x-r, 0) + 1;
      tmp[row+x] = acc / n;
    }
  }
  for (let x = 0; x < w; x++){
    let acc = 0;
    for (let y = 0; y < Math.min(r, h); y++) acc += tmp[y*w+x];
    for (let y = 0; y < h; y++){
      const add = y + r, sub = y - r - 1;
      if (add < h) acc += tmp[add*w+x];
      if (sub >= 0) acc -= tmp[sub*w+x];
      const n = Math.min(y+r, h-1) - Math.max(y-r, 0) + 1;
      out[y*w+x] = acc / n;
    }
  }
  return out;
}

function otsu(gray){
  const hist = new Float64Array(256);
  for (let i = 0; i < gray.length; i++) hist[Math.max(0, Math.min(255, gray[i]|0))]++;
  const total = gray.length;
  let sumAll = 0; for (let t = 0; t < 256; t++) sumAll += t * hist[t];
  let w0 = 0, s0 = 0, best = -1, thr = 128;
  for (let t = 0; t < 256; t++){
    w0 += hist[t]; if (!w0) continue;
    const w1 = total - w0; if (!w1) break;
    s0 += t * hist[t];
    const m0 = s0 / w0, m1 = (sumAll - s0) / w1;
    const v = w0 * w1 * (m0 - m1) * (m0 - m1);
    if (v > best){ best = v; thr = t; }
  }
  return thr;
}

/** 连通域标记（4 邻接，迭代 BFS）→ {labels, sizes} */
function connected(mask, w, h){
  const labels = new Int32Array(mask.length), sizes = [0];
  const stack = new Int32Array(mask.length);
  let cur = 0;
  for (let p = 0; p < mask.length; p++){
    if (!mask[p] || labels[p]) continue;
    cur++; let sp = 0, size = 0;
    stack[sp++] = p; labels[p] = cur;
    while (sp){
      const q = stack[--sp]; size++;
      const x = q % w, y = (q / w) | 0;
      if (x > 0   && mask[q-1] && !labels[q-1]){ labels[q-1]=cur; stack[sp++]=q-1; }
      if (x < w-1 && mask[q+1] && !labels[q+1]){ labels[q+1]=cur; stack[sp++]=q+1; }
      if (y > 0   && mask[q-w] && !labels[q-w]){ labels[q-w]=cur; stack[sp++]=q-w; }
      if (y < h-1 && mask[q+w] && !labels[q+w]){ labels[q+w]=cur; stack[sp++]=q+w; }
    }
    sizes.push(size);
  }
  return {labels, sizes};
}

function denoiseAlpha(alpha, w, h, minFrac){
  const mask = new Uint8Array(alpha.length);
  for (let i = 0; i < alpha.length; i++) mask[i] = alpha[i] > 40 ? 1 : 0;
  const {labels, sizes} = connected(mask, w, h);
  if (sizes.length <= 1) return alpha;
  const maxSize = Math.max(...sizes.slice(1));
  const cut = Math.max(6, maxSize * minFrac);
  const out = Float32Array.from(alpha);
  for (let i = 0; i < out.length; i++){
    const l = labels[i];
    if (l && sizes[l] < cut) out[i] = 0;
  }
  return out;
}

/**
 * 剥签名栏长横线。⚠ 不能用「连通域长宽比判扁」——签名笔画常穿过横线、两者同属
 * 一个连通域，整域一点也不扁（实测 0 删除）。正解 = 水平结构元开运算。
 * 返回 {alpha, delta}，delta = 墨占比降幅；为 0 说明没检出横线（no-op）。
 */
function removeRuleLine(alpha, w, h){
  const before = inkRatio(alpha);
  const L = Math.max(15, Math.round(w * 0.35));
  const solid = new Float32Array(alpha.length);
  for (let i = 0; i < alpha.length; i++) solid[i] = alpha[i] > 40 ? 1 : 0;
  // 水平开运算 = 水平腐蚀 → 水平膨胀
  const eroded  = slide1d(solid,  w, h, L, true, 'min');
  const opened  = slide1d(eroded, w, h, L, true, 'max');
  let lineCount = 0;
  for (let i = 0; i < opened.length; i++) if (opened[i] > 0.5) lineCount++;
  if (!lineCount) return {alpha, delta:0};
  // 纵向膨胀 3，带走抗锯齿边
  const line = slide1d(opened, w, h, 3, false, 'max');
  const out = Float32Array.from(alpha);
  let thickness = 3;
  for (let x = 0; x < w; x++){
    let c = 0; for (let y = 0; y < h; y++) if (line[y*w+x] > 0.5) c++;
    if (c > thickness) thickness = c;
  }
  for (let i = 0; i < out.length; i++) if (line[i] > 0.5) out[i] = 0;
  // 桥接：竖笔穿过横线处被切出断口 → 纵向闭运算（膨胀后腐蚀），
  // 只有该列横线上下都还有墨时才接得上，纯横线区上下无墨不会复活。
  const kk = 2 * thickness + 5;
  const dil = slide1d(out, w, h, kk, false, 'max');
  const clo = slide1d(dil, w, h, kk, false, 'min');
  for (let i = 0; i < out.length; i++) if (line[i] > 0.5 && clo[i] > out[i]) out[i] = clo[i];
  const cleaned = denoiseAlpha(out, w, h, 0.01);
  return {alpha: cleaned, delta: before - inkRatio(cleaned)};
}

function inkRatio(alpha){
  let n = 0; for (let i = 0; i < alpha.length; i++) if (alpha[i] > 40) n++;
  return n / alpha.length;
}

/** 主流程：ImageData → {canvas, stats} */
function extract(imgData, opts){
  const {width:w, height:h, data:d} = imgData;
  const gray = new Float32Array(w*h);
  for (let i = 0, p = 0; i < d.length; i += 4, p++)
    gray[p] = 0.299*d[i] + 0.587*d[i+1] + 0.114*d[i+2];

  // 背景归一化：局部最亮（=纸）作背景，除掉它 → 吃掉拍照光照不均
  let k = Math.max(9, Math.round(Math.min(w, h) * 0.12)); if (!(k & 1)) k++;
  const bgMax = slide1d(slide1d(gray, w, h, k, true, 'max'), w, h, k, false, 'max');
  const bg = boxBlur(bgMax, w, h, k);
  const flat = new Float32Array(w*h);
  for (let i = 0; i < flat.length; i++)
    flat[i] = Math.max(0, Math.min(255, gray[i] / Math.max(bg[i], 1) * 255));

  const thr = Math.max(20, Math.min(240, otsu(flat) + (opts.bias || 0)));
  const dark = thr * 0.55, light = Math.min(thr * 1.06, 250);
  let alpha = new Float32Array(w*h);
  for (let i = 0; i < alpha.length; i++)
    alpha[i] = Math.max(0, Math.min(1, (light - flat[i]) / Math.max(light - dark, 1))) * 255;

  if (opts.denoise) alpha = denoiseAlpha(alpha, w, h, 0.004);
  let delineDelta = null;
  if (opts.deline){ const r = removeRuleLine(alpha, w, h); alpha = r.alpha; delineDelta = r.delta; }

  const ratio = inkRatio(alpha);
  if (ratio < MIN_INK || ratio > MAX_INK)
    return {error:`墨迹占比 ${(ratio*100).toFixed(2)}% 超出 0.3%–45% —— 阈值判飞了。这张可能不是「深墨浅纸」的签名照，或曝光太暗。`};

  // 墨色
  let ink = INKS[opts.ink] || INKS.black;
  if (opts.ink === 'custom'){
    const m = /^#?([0-9a-f]{6})$/i.exec(opts.inkCustom || '');
    if (m) ink = [0,2,4].map(i => parseInt(m[1].substr(i,2), 16));
  } else if (opts.ink === 'auto'){
    let r=0,g=0,b=0,n=0;
    for (let i=0,p=0; i<d.length; i+=4,p++) if (alpha[p] > 180){ r+=d[i]; g+=d[i+1]; b+=d[i+2]; n++; }
    if (n > 20){ const mean = Math.max((r+g+b)/(3*n), 1), f = 60/mean;
      ink = [r/n*f, g/n*f, b/n*f].map(c => Math.max(0, Math.min(255, Math.round(c)))); }
  }

  // 裁到墨迹包围盒 + pad
  const pad = 8;
  let x0=w, y0=h, x1=-1, y1=-1;
  for (let y=0; y<h; y++) for (let x=0; x<w; x++)
    if (alpha[y*w+x] > 25){ if(x<x0)x0=x; if(x>x1)x1=x; if(y<y0)y0=y; if(y>y1)y1=y; }
  x0 = Math.max(0, x0-pad); y0 = Math.max(0, y0-pad);
  x1 = Math.min(w-1, x1+pad); y1 = Math.min(h-1, y1+pad);
  const cw = x1-x0+1, ch = y1-y0+1;

  const base = document.createElement('canvas');
  base.width = cw; base.height = ch;
  const bctx = base.getContext('2d');
  const od = bctx.createImageData(cw, ch);
  for (let y=0; y<ch; y++) for (let x=0; x<cw; x++){
    const s = (y+y0)*w + (x+x0), t = (y*cw + x)*4;
    od.data[t]=ink[0]; od.data[t+1]=ink[1]; od.data[t+2]=ink[2];
    od.data[t+3]=Math.round(alpha[s]);
  }
  bctx.putImageData(od, 0, 0);

  const s = Math.max(1, opts.scale|0);
  let final = base;
  if (s > 1){
    final = document.createElement('canvas');
    final.width = cw*s; final.height = ch*s;
    const fctx = final.getContext('2d');
    fctx.imageSmoothingEnabled = true; fctx.imageSmoothingQuality = 'high';
    fctx.drawImage(base, 0, 0, final.width, final.height);
  }
  return {canvas: final, thr, ratio, ink, delineDelta, cm: final.width/300*2.54};
}

/* ── PNG 写 300dpi（canvas.toBlob 不带 pHYs，手工插一个）─────────────────── */
const CRC_T = (() => { const t = new Uint32Array(256);
  for (let n=0;n<256;n++){ let c=n; for(let k=0;k<8;k++) c = c&1 ? 0xEDB88320 ^ (c>>>1) : c>>>1; t[n]=c>>>0; }
  return t; })();
function crc32(buf){ let c = 0xFFFFFFFF;
  for (let i=0;i<buf.length;i++) c = CRC_T[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0; }
function withDpi(arrayBuffer, dpi){
  const src = new Uint8Array(arrayBuffer);
  const ppm = Math.round(dpi / 0.0254);           // pixels per metre
  const chunk = new Uint8Array(21);
  const dv = new DataView(chunk.buffer);
  dv.setUint32(0, 9);                              // length
  chunk.set([0x70,0x48,0x59,0x73], 4);             // "pHYs"
  dv.setUint32(8, ppm); dv.setUint32(12, ppm);
  chunk[16] = 1;                                   // unit = metre
  dv.setUint32(17, crc32(chunk.subarray(4, 17)));
  // 插在 IHDR（8 + 25 字节）之后
  const at = 8 + 25;
  const out = new Uint8Array(src.length + chunk.length);
  out.set(src.subarray(0, at), 0);
  out.set(chunk, at);
  out.set(src.subarray(at), at + chunk.length);
  return out;
}


  window.SigCore = {extract, otsu, removeRuleLine, denoiseAlpha, inkRatio, slide1d, boxBlur,
                  connected, withDpi, crc32, MIN_INK, MAX_INK, INKS};
})();
