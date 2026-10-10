#!/usr/bin/env python3
"""签名照片 → 电子签名 PNG（透明底 + 纯墨迹 + 裁边 + 打印 dpi）。

为什么阈值要自适应：手机拍的签名纸底 90~230 都有（光照不均），手调 level 必然每张试三轮。
Otsu 在「墨/纸」这种双峰分布上是标准解，配合背景归一化（rolling-ball 近似）可吃掉阴影。

用法
  python3 sig_extract.py IMG [IMG...] -o OUTDIR [--ink black|blue|auto|#RRGGBB]
                         [--deline] [--scale 4] [--dpi 300] [--preview] [--pad 8]

机器门（fail-closed）
  - 输入枚举为空          → exit 2
  - 墨迹占比 <0.3% 或 >45% → exit 2（阈值判飞了，不许静默交一张空图或一张黑图）
  - 输出文件不存在/0 字节  → exit 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

INK_PRESETS = {
    "black": (0, 0, 0),
    "blue": (26, 58, 143),      # 深蓝墨水，打印/扫描件常见
    "darkblue": (12, 35, 92),
}
class GateError(RuntimeError):
    """机器门失败 → 统一 exit 2。"""


MIN_INK_RATIO = 0.003           # 低于此 = 几乎没抠出东西
MAX_INK_RATIO = 0.45            # 高于此 = 把纸底也当墨了


def _otsu(gray: np.ndarray) -> float:
    """双峰灰度的 Otsu 阈值（0-255 浮点）。"""
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    total = hist.sum()
    if total == 0:
        return 128.0
    w0 = np.cumsum(hist)
    w1 = total - w0
    idx = np.arange(256)
    s0 = np.cumsum(hist * idx)
    s_total = s0[-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        m0 = s0 / w0
        m1 = (s_total - s0) / w1
        var_between = w0 * w1 * (m0 - m1) ** 2
    var_between[~np.isfinite(var_between)] = -1
    return float(np.argmax(var_between))


def _flatten_background(gray: np.ndarray) -> np.ndarray:
    """除以局部背景估计，压掉拍照的光照不均/阴影。返回 0-255。"""
    # 背景 = 大核灰度膨胀（取局部最亮=纸），核大到吞掉笔画宽度
    k = max(9, int(min(gray.shape) * 0.12) | 1)
    bg = ndimage.grey_dilation(gray, size=(k, k))
    bg = ndimage.uniform_filter(bg, size=k)
    bg = np.maximum(bg, 1.0)
    return np.clip(gray / bg * 255.0, 0, 255)


def _denoise(alpha: np.ndarray, min_frac: float = 0.004) -> np.ndarray:
    """删掉面积远小于主笔画的孤立连通域（纸纹/污点/扫描噪声）。"""
    mask = alpha > 40
    lab, n = ndimage.label(mask)
    if n == 0:
        return alpha
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    keep = np.zeros(n + 1, dtype=bool)
    keep[1:] = sizes >= max(6.0, sizes.max() * min_frac)
    out = alpha.copy()
    out[~keep[lab]] = 0
    return out


def _remove_rule_line(alpha: np.ndarray, min_span: float = 0.35) -> np.ndarray:
    """剥掉签名栏的长水平横线。

    ⚠ 不能用「连通域长宽比判扁」——签名笔画常穿过横线，两者是同一个连通域，
    整域的长宽比看起来一点也不扁（2026-08-14 实测：那条路 0 删除）。
    正确解 = 水平结构元的开运算：只有连续水平长度 ≥ L 的像素能活下来，
    签名里最长的横向笔画也远短于 L，所以提取出的就是那条直线本身。
    交叉处减完会缺一小口，用一次小闭运算补回。
    """
    h, w = alpha.shape
    L = max(15, int(w * min_span))
    solid = (alpha > 40).astype(np.uint8)
    line = ndimage.binary_opening(solid, structure=np.ones((1, L)))
    if line.sum() == 0:
        return alpha
    # 横线一般只有几像素厚；纵向膨胀一点把抗锯齿边一并带走
    line = ndimage.binary_dilation(line, structure=np.ones((3, 1))).astype(bool)
    thickness = max(3, int(line.sum(axis=0).max()))
    out = alpha.copy()
    out[line] = 0

    # 桥接：竖笔穿过横线处会被切出断口。在删除区内做纵向闭运算——
    # 只有该列在横线上下都还有墨时才会被接上，纯横线区上下无墨不会复活。
    bridge = ndimage.grey_closing(out, size=(2 * thickness + 5, 1))
    out = np.where(line, np.maximum(out, bridge), out)

    # 二次清扫被切断的横线残段
    return _denoise(out, min_frac=0.01)


def _resolve_ink(name: str, rgb_src: np.ndarray | None, alpha: np.ndarray):
    if name == "auto":
        if rgb_src is None:
            return INK_PRESETS["black"]
        sel = alpha > 180
        if sel.sum() < 20:
            return INK_PRESETS["black"]
        med = np.median(rgb_src[sel], axis=0)
        # 压暗到墨色（保留色相，避免灰蒙蒙）
        med = med * (60.0 / max(med.mean(), 1.0))
        return tuple(int(np.clip(c, 0, 255)) for c in med)
    if name in INK_PRESETS:
        return INK_PRESETS[name]
    s = name.lstrip("#")
    if len(s) == 6:
        try:
            return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    raise GateError(f"未知墨色: {name}（要 black/blue/darkblue/auto 或 #RRGGBB）")


def extract(src: Path, dst: Path, *, ink="black", scale=4, dpi=300,
            deline=False, denoise=True, pad=8) -> dict:
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    rgb = np.asarray(im).astype(np.float32)
    gray = np.asarray(im.convert("L")).astype(np.float32)

    flat = _flatten_background(gray)
    thr = _otsu(flat)
    # 软 alpha: thr 附近线性过渡保抗锯齿; 墨心(thr*0.55)以下全不透明
    dark, light = thr * 0.55, min(thr * 1.06, 250.0)
    alpha = np.clip((light - flat) / max(light - dark, 1.0), 0, 1) * 255.0

    if denoise:
        alpha = _denoise(alpha)

    # 变换生效断言：flag 说要做的事，必须能拿出「前后差分」证明它真发生了。
    # 2026-08-14 踩坑：--deline 第一版判据错，跑完墨占比与不加 flag 一模一样（0 删除），
    # 输出图看着正常、退出码 0，差点当「去线版」交出去。静默 no-op 是最难发现的假绿。
    deline_delta = None
    if deline:
        before = float((alpha > 40).mean())
        alpha = _remove_rule_line(alpha)
        deline_delta = before - float((alpha > 40).mean())

    ratio = float((alpha > 40).mean())
    if not (MIN_INK_RATIO <= ratio <= MAX_INK_RATIO):
        raise GateError(
            f"{src.name}: 墨迹占比 {ratio:.3%} 超出 "
            f"[{MIN_INK_RATIO:.1%},{MAX_INK_RATIO:.0%}] —— 阈值判飞，拒绝输出。"
            f" 源图可能不是「深墨浅纸」的签名照。"
        )

    ink_rgb = _resolve_ink(ink, rgb, alpha)

    # 裁到墨迹包围盒
    ys, xs = np.where(alpha > 25)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, alpha.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, alpha.shape[1])
    alpha = alpha[y0:y1, x0:x1]

    a_img = Image.fromarray(alpha.astype(np.uint8), "L")
    if scale and scale != 1:
        a_img = a_img.resize((a_img.width * scale, a_img.height * scale), Image.LANCZOS)

    out = Image.new("RGBA", a_img.size, ink_rgb + (0,))
    out.putalpha(a_img)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, dpi=(dpi, dpi))

    if not dst.exists() or dst.stat().st_size == 0:
        raise GateError(f"输出为空: {dst}")

    cm = out.width / dpi * 2.54
    return {"out": dst, "w": out.width, "h": out.height, "ratio": ratio,
            "thr": thr, "ink": ink_rgb, "cm": cm, "deline_delta": deline_delta}


def make_preview(items, dst: Path):
    """白底 + 灰格底并排对照，供人/主会话 Read 验收（不是交付件）。"""
    tiles = []
    for it in items:
        im = Image.open(it["out"]).convert("RGBA")
        w = 600
        im = im.resize((w, max(1, int(im.height * w / im.width))), Image.LANCZOS)
        white = Image.new("RGBA", im.size, (255, 255, 255, 255))
        white.alpha_composite(im)
        chk = Image.new("RGBA", im.size, (255, 255, 255, 255))
        px = chk.load()
        for y in range(0, im.height, 16):
            for x in range(0, im.width, 16):
                if (x // 16 + y // 16) % 2:
                    for yy in range(y, min(y + 16, im.height)):
                        for xx in range(x, min(x + 16, im.width)):
                            px[xx, yy] = (214, 214, 214, 255)
        chk.alpha_composite(im)
        row = Image.new("RGBA", (im.width * 2 + 12, im.height), (150, 150, 150, 255))
        row.paste(white, (0, 0)); row.paste(chk, (im.width + 12, 0))
        tiles.append(row)
    W = max(t.width for t in tiles)
    H = sum(t.height for t in tiles) + 12 * (len(tiles) - 1)
    canvas = Image.new("RGB", (W, H), (150, 150, 150))
    y = 0
    for t in tiles:
        canvas.paste(t.convert("RGB"), (0, y)); y += t.height + 12
    canvas.save(dst)
    return dst


def main():
    ap = argparse.ArgumentParser(description="签名照片 → 透明底电子签名 PNG")
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("-o", "--outdir", type=Path, required=True)
    ap.add_argument("--ink", default="black",
                    help="black(默认)/blue/darkblue/auto/#RRGGBB")
    ap.add_argument("--scale", type=int, default=4, help="上采样倍数(默认4)")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--pad", type=int, default=8)
    ap.add_argument("--deline", action="store_true", help="剥掉签名栏长横线")
    ap.add_argument("--no-denoise", dest="denoise", action="store_false")
    ap.add_argument("--preview", action="store_true", help="额外出白底/格底对照图")
    ap.add_argument("--suffix", default="", help="输出文件名后缀，如 -blue")
    a = ap.parse_args()

    srcs = [p for p in a.images if p.is_file()]
    if not srcs:
        print("[FAIL] 输入枚举为空，拒绝在空集上报绿。", file=sys.stderr)
        sys.exit(2)

    a.outdir.mkdir(parents=True, exist_ok=True)
    results = []
    for s in srcs:
        dst = a.outdir / f"{s.stem}{a.suffix}.png"
        r = extract(s, dst, ink=a.ink, scale=a.scale, dpi=a.dpi,
                    deline=a.deline, denoise=a.denoise, pad=a.pad)
        results.append(r)
        print(f"✓ {r['out']}  {r['w']}x{r['h']}px  墨占比 {r['ratio']:.2%}  "
              f"Otsu={r['thr']:.0f}  ink=rgb{r['ink']}  @{a.dpi}dpi≈{r['cm']:.1f}cm 宽")
        d = r["deline_delta"]
        if d is not None:
            if d <= 0.0005:
                print("  ⚠ --deline 未检出横线，本次是 no-op —— 输出与不加该 flag 完全相同。"
                      "别把它当「去线版」交出去。", file=sys.stderr)
            else:
                print(f"  剥线生效: 墨占比 -{d:.2%}")

    if a.preview:
        p = make_preview(results, a.outdir / "_preview.png")
        print(f"→ 对照预览(左白底/右格底): {p}")


if __name__ == "__main__":
    try:
        main()
    except GateError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        sys.exit(2)
