#!/usr/bin/env python3
"""gta6-clipper-01 v6 — render the clip.

Fresh, deterministic, single-purpose renderer for the v6 entry:
  "He drove a supercar off the Vice City bridge... and LANDED it on a MOVING YACHT"

Vertical 1080x1920, 30 fps, 30.0 s. Every frame is drawn with PIL from
closed-form functions of time (no randomness except a fixed-seed LCG for
star/particle placement, so re-runs are byte-identical). Audio is
synthesised with numpy (128 BPM beat + engine/wind/impact/splash SFX).
Video is piped as raw RGB into a single-thread libx264 encode.

Usage: python3 render_video.py <out.mp4>
"""
import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FPS = 30
DUR = 30.0
NFRAMES = int(DUR * FPS)
SR = 48000

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(size, bold=True):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, int(size))


# ---------------------------------------------------------------- deterministic LCG
def lcg(n, seed=1234567):
    out = []
    x = seed
    for _ in range(n):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        out.append(x / 0x7FFFFFFF)
    return out


STARS = [(lcg(120, 99)[i] * W, lcg(120, 77)[i] * 700) for i in range(120)]
STAR_R = lcg(120, 55)


def vgrad(top, bottom):
    """Vertical gradient as an RGB image."""
    t = np.linspace(0, 1, H)[:, None]
    top = np.array(top, dtype=np.float64)
    bottom = np.array(bottom, dtype=np.float64)
    arr = (top[None, :] * (1 - t) + bottom[None, :] * t).astype(np.uint8)
    return Image.fromarray(np.repeat(arr[:, None, :], W, axis=1), "RGB")


def sky_dusk():
    return vgrad((26, 12, 64), (255, 110, 60))


def sky_night():
    return vgrad((8, 8, 34), (58, 20, 88))


def draw_stars(dr, t):
    for i, (sx, sy) in enumerate(STARS):
        tw = 0.5 + 0.5 * math.sin(t * 2.0 + i)
        a = int(90 + 140 * tw)
        r = 1 + STAR_R[i] * 1.6
        dr.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(255, 255, 255, a))


def sun(dr, cx, cy, r, core=(255, 214, 120), glow=(255, 140, 60)):
    dr.ellipse([cx - r * 1.7, cy - r * 1.7, cx + r * 1.7, cy + r * 1.7],
               fill=glow + (22,))
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=core + (255,))


def skyline(dr, base_y, color, seed, scale=1.0):
    """Fixed building silhouettes with lit windows."""
    rnd = lcg(90, seed)
    x = -20.0
    i = 0
    while x < W + 40:
        bw = (60 + rnd[i % 90] * 130) * scale
        bh = (120 + rnd[(i + 7) % 90] * 420) * scale
        dr.rectangle([x, base_y - bh, x + bw, base_y], fill=color + (255,))
        # lit windows
        wx, wy = x + 10, base_y - bh + 14
        while wy < base_y - 14:
            while wx < x + bw - 12:
                if rnd[(i * 3 + int(wx)) % 90] > 0.55:
                    dr.rectangle([wx, wy, wx + 7, wy + 10],
                                 fill=(255, 214, 120, 200))
                wx += 18
            wx = x + 10
            wy += 26
        x += bw + 8
        i += 1


def palm(dr, x, base_y, s, color=(10, 26, 18, 255)):
    dr.line([x, base_y, x + 14 * s, base_y - 150 * s], fill=color, width=int(10 * s))
    cx, cy = x + 14 * s, base_y - 150 * s
    for ang in (-150, -115, -80, -45, -10, 25):
        a = math.radians(ang)
        ex, ey = cx + math.cos(a) * 100 * s, cy + math.sin(a) * 46 * s + 34 * s
        mx, my = cx + math.cos(a) * 55 * s, cy + math.sin(a) * 10 * s - 26 * s
        dr.line([cx, cy, mx, my, ex, ey], fill=color, width=int(6 * s),
                joint="curve")


def water(dr, top_y, t, base=(16, 42, 92)):
    dr.rectangle([0, top_y, W, H], fill=base + (255,))
    # moving wave highlights
    for row in range(14):
        y = top_y + 18 + row * 34
        amp = 6 + row * 0.8
        pts = []
        for px in range(0, W + 20, 20):
            pts.append((px, y + amp * math.sin(px * 0.012 + t * 1.7 + row * 0.9)))
        dr.line(pts, fill=(90, 160, 255, 70), width=3)
    # sun reflection column
    for k in range(26):
        y = top_y + 10 + k * 26
        wdt = 36 + 120 * (k / 26.0) + 12 * math.sin(t * 2.4 + k)
        a = int(110 * (1 - k / 30.0))
        dr.rectangle([W / 2 - wdt / 2, y, W / 2 + wdt / 2, y + 5],
                     fill=(255, 170, 80, a))


def bridge_deck(dr, y, t, speed=1.0):
    """Bridge deck across the lower frame + pillars + cables."""
    dr.rectangle([0, y, W, H], fill=(24, 24, 34, 255))
    # lane dashes streaking past (small, low)
    off = (t * 900 * speed) % 160
    for k in range(-2, 9):
        x = k * 160 - off
        dr.polygon([(x, y + 150), (x + 26, y + 150), (x + 44, y + 240), (x + 6, y + 240)],
                   fill=(255, 214, 80, 200))
    # guard rail
    dr.rectangle([0, y - 26, W, y - 6], fill=(70, 74, 96, 255))
    for px in range(0, W + 180, 180):
        dr.line([px, y - 26, px + 14, y - 90], fill=(70, 74, 96, 255), width=7)
    # cables (sparse, faint)
    for px in range(90, W + 360, 360):
        dr.line([px, y - 26, px + 60, y - 300], fill=(120, 124, 150, 90), width=3)


def car(dr, cx, cy, s, wheel_turn, body=(232, 28, 52), glow=True):
    """Side-view supercar, nose pointing right."""
    if glow:
        dr.ellipse([cx - 230 * s, cy + 44 * s, cx + 230 * s, cy + 96 * s],
                   fill=(255, 60, 90, 28))
    # body
    dr.polygon([(cx - 230 * s, cy + 40 * s), (cx - 210 * s, cy - 22 * s),
                (cx - 120 * s, cy - 58 * s), (cx - 40 * s, cy - 88 * s),
                (cx + 90 * s, cy - 82 * s), (cx + 170 * s, cy - 40 * s),
                (cx + 235 * s, cy + 10 * s), (cx + 225 * s, cy + 40 * s)],
               fill=body + (255,))
    # cabin glass
    dr.polygon([(cx - 100 * s, cy - 56 * s), (cx - 38 * s, cy - 80 * s),
                (cx + 78 * s, cy - 74 * s), (cx + 130 * s, cy - 38 * s),
                (cx - 20 * s, cy - 34 * s)], fill=(150, 220, 255, 235))
    # headlight beam
    dr.polygon([(cx + 225 * s, cy - 6 * s), (cx + 480 * s, cy - 60 * s),
                (cx + 480 * s, cy + 30 * s), (cx + 225 * s, cy + 22 * s)],
               fill=(255, 244, 180, 70))
    dr.ellipse([cx + 205 * s, cy - 8 * s, cx + 232 * s, cy + 12 * s],
               fill=(255, 250, 200, 255))
    # wheels
    for wx in (cx - 140 * s, cx + 140 * s):
        dr.ellipse([wx - 46 * s, cy - 6 * s, wx + 46 * s, cy + 86 * s],
                   fill=(12, 12, 16, 255))
        dr.ellipse([wx - 24 * s, cy + 16 * s, wx + 24 * s, cy + 64 * s],
                   fill=(200, 200, 210, 255))
        for k in range(5):
            a = wheel_turn + k * (2 * math.pi / 5)
            dr.line([wx, cy + 40 * s, wx + 22 * s * math.cos(a),
                     cy + 40 * s + 22 * s * math.sin(a)],
                    fill=(30, 30, 36, 255), width=6)


def yacht(dr, cx, cy, s, t):
    """White yacht, bow pointing right, gentle bob."""
    bob = 6 * math.sin(t * 1.4)
    cy += bob
    # hull
    dr.polygon([(cx - 300 * s, cy), (cx + 300 * s, cy - 30 * s),
                (cx + 260 * s, cy + 70 * s), (cx - 260 * s, cy + 70 * s)],
               fill=(240, 244, 248, 255))
    dr.polygon([(cx - 300 * s, cy), (cx + 300 * s, cy - 30 * s),
                (cx + 280 * s, cy - 6 * s), (cx - 280 * s, cy + 18 * s)],
               fill=(30, 90, 180, 255))
    # cabin
    dr.rounded_rectangle([cx - 150 * s, cy - 120 * s, cx + 90 * s, cy - 10 * s],
                         radius=18, fill=(250, 250, 252, 255))
    for k in range(4):
        dr.rectangle([cx - 130 * s + k * 58 * s, cy - 100 * s,
                      cx - 100 * s + k * 58 * s, cy - 60 * s],
                     fill=(120, 200, 255, 255))
    # mast + flag
    dr.line([cx + 40 * s, cy - 120 * s, cx + 40 * s, cy - 240 * s],
            fill=(220, 224, 230, 255), width=8)
    dr.polygon([(cx + 40 * s, cy - 240 * s), (cx + 120 * s, cy - 222 * s),
                (cx + 40 * s, cy - 204 * s)], fill=(255, 60, 90, 255))
    # wake
    for k in range(6):
        ww = 60 + k * 46
        dr.arc([cx - 330 * s - ww, cy + 66 * s - 14, cx - 260 * s - ww + 90,
                cy + 66 * s + 26], start=200, end=340,
               fill=(255, 255, 255, 150), width=5)
    return cy


def splash(dr, cx, cy, t01, s=1.0):
    """Expanding rings + droplets after the landing."""
    for k in range(3):
        r = (t01 * 420 + k * 60) * s
        a = max(0, int(230 * (1 - t01) - k * 40))
        dr.ellipse([cx - r, cy - r * 0.32, cx + r, cy + r * 0.32],
                   outline=(255, 255, 255, a), width=7)
    rnd = lcg(40, 4242)
    for i in range(40):
        ang = rnd[i] * math.pi * 2
        dist = (60 + rnd[(i + 5) % 40] * 320) * t01 * s
        dx = math.cos(ang) * dist
        dy = -abs(math.sin(ang)) * dist * 1.4 - t01 * 120 * s
        a = max(0, int(255 * (1 - t01)))
        dr.ellipse([cx + dx - 5, cy + dy - 5, cx + dx + 5, cy + dy + 5],
                   fill=(220, 240, 255, a))


def speed_lines(dr, t, n=14, color=(255, 255, 255, 150)):
    rnd = lcg(n * 2, 777)
    for i in range(n):
        y = rnd[i] * H
        x0 = (rnd[i + n] * W + t * 2600) % (W + 600) - 300
        ln = 120 + rnd[i] * 260
        dr.line([x0, y, x0 + ln, y - 26], fill=color, width=5)


# ---------------------------------------------------------------- text helpers
def text_layer():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def fit_size(text, size, max_width=1000):
    """Shrink a font size until the text fits max_width."""
    while size > 24:
        f = font(size)
        if f.getlength(text) <= max_width:
            return size
        size -= 4
    return size


def draw_text(dr, cx, y, text, size, fill=(255, 255, 255), stroke=10,
              stroke_fill=(0, 0, 0), anchor="ma", max_width=1000):
    size = fit_size(text, size, max_width)
    f = font(size)
    dr.text((cx, y), text, font=f, fill=fill + (255,), anchor=anchor,
            stroke_width=stroke, stroke_fill=stroke_fill + (255,))


def pop_in(base, layer, t01):
    """Scale+fade a text layer in over the first 0.25 of its life."""
    p = min(1.0, t01 / 0.25)
    ease = 1 - (1 - p) ** 3
    a = int(255 * ease)
    if a <= 0:
        return base
    sc = 1.18 - 0.18 * ease
    w2, h2 = int(W * sc), int(H * sc)
    small = layer.resize((w2, h2), Image.LANCZOS)
    lx, ly = (W - w2) // 2, (H - h2) // 2
    alpha = small.split()[3].point(lambda v: v * a // 255)
    small.putalpha(alpha)
    base.paste(small, (lx, ly), small)
    return base


def vignette(img):
    ov = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(ov)
    d.ellipse([-W * 0.25, -H * 0.18, W * 1.25, H * 1.18], fill=255)
    ov = ov.point(lambda v: 255 - int((255 - v) * 0.28))
    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(img, black, ov)


def shake(img, t, t0, dur, amp=14):
    if not (t0 <= t < t0 + dur):
        return img
    p = (t - t0) / dur
    dx = amp * (1 - p) * math.sin(t * 91.0)
    dy = amp * (1 - p) * math.cos(t * 77.0)
    out = Image.new("RGB", (W, H), (0, 0, 0))
    out.paste(img, (int(dx), int(dy)))
    return out

# ---------------------------------------------------------------- scenes
def scene_hook(t):
    """0-3s: HOOK. Dusk sky, bridge, car launching off the ramp."""
    img = sky_dusk().convert("RGBA")
    dr = ImageDraw.Draw(img, "RGBA")
    draw_stars(dr, t)
    sun(dr, 780, 430, 64)
    skyline(dr, 1180, (30, 16, 58), seed=11)
    # bay strip
    dr.rectangle([0, 1180, W, 1330], fill=(20, 44, 92, 255))
    for k in range(4):
        y = 1200 + k * 34
        dr.line([(0, y), (W, y)], fill=(90, 160, 255, 60), width=3)
    # ramp + launching car
    dr.polygon([(120, 1330), (960, 1330), (960, 1420), (60, 1420)],
               fill=(24, 24, 34, 255))
    dr.polygon([(700, 1330), (960, 1330), (960, 1420), (760, 1420)],
               fill=(255, 170, 40, 255))
    cx = 620 + t * 130
    cy = 1290 - 190 * (t / 3.0) ** 2
    car(dr, cx, cy, 1.0, t * 9)
    speed_lines(dr, t, n=10)
    # open water below the bridge + the distant yacht waiting below
    water(dr, 1420, t)
    yacht(dr, 760, 1760, 0.62, t)
    img = img.convert("RGB")
    # hook text
    layer, ldr = text_layer()
    p = min(1.0, t / 3.0)
    draw_text(ldr, W // 2, 300, "HE DROVE OFF", 148, fill=(255, 255, 255))
    draw_text(ldr, W // 2, 470, "THE BRIDGE", 148, fill=(255, 214, 80))
    if t > 1.6:
        draw_text(ldr, W // 2, 700, "WAIT FOR IT...", 72, fill=(255, 255, 255))
    img = pop_in(img, layer, p)
    return vignette(img)


def scene_reveal(t):
    """3-8s: car hammering along the bridge toward the ramp."""
    lt = t - 3.0
    img = sky_night().convert("RGBA")
    dr = ImageDraw.Draw(img, "RGBA")
    draw_stars(dr, t)
    sun(dr, 300, 360, 54, core=(255, 230, 160))
    skyline(dr, 1080, (16, 10, 40), seed=23)
    bridge_deck(dr, 1150, t, speed=1.6)
    water(dr, 1560, t)
    # car approaches from the left, grows as it nears the ramp
    prog = lt / 5.0
    cx = 120 + prog * 760
    s = 0.85 + prog * 0.45
    car(dr, cx, 1180, s, t * 26)
    speed_lines(dr, t, n=16)
    img = img.convert("RGB")
    layer, ldr = text_layer()
    draw_text(ldr, W // 2, 300, "5 STARS. NO BRAKES.", 84, fill=(255, 255, 255))
    if lt > 2.2:
        draw_text(ldr, W // 2, 1420, "ONE RAMP. ONE SHOT.", 76,
                  fill=(255, 214, 80))
    img = pop_in(img, layer, min(1.0, lt / 5.0))
    return vignette(img)


def scene_air(t):
    """8-16s: the car sails over the bay; the yacht cruises below."""
    lt = t - 8.0
    p = lt / 8.0
    img = sky_dusk().convert("RGBA")
    dr = ImageDraw.Draw(img, "RGBA")
    draw_stars(dr, t)
    sun(dr, 540, 500, 64)
    skyline(dr, 900, (40, 20, 66), seed=31)
    water(dr, 900, t)
    # yacht moving right below
    yx = 180 + p * 620
    yacht(dr, yx, 1480, 1.05, t)
    # parabolic arc: launch (180,1150) -> apex (540,520) -> target yacht deck
    x0, y0, x1, y1 = 150.0, 1120.0, yx + 40, 1400.0
    apex_y = 480.0
    cx = x0 + (x1 - x0) * p
    cy = (1 - p) ** 2 * y0 + 2 * (1 - p) * p * apex_y + p ** 2 * y1
    car(dr, cx, cy, 1.15, t * 6)
    speed_lines(dr, t, n=8, color=(255, 255, 255, 110))
    img = img.convert("RGB")
    layer, ldr = text_layer()
    draw_text(ldr, W // 2, 300, "HE'S AIMING FOR", 92, fill=(255, 255, 255))
    draw_text(ldr, W // 2, 420, "THE YACHT", 132, fill=(255, 214, 80))
    alt = int(140 * (1 - p) + 8)
    draw_text(ldr, W // 2, 1500, f"ALT {alt}m", 54, fill=(255, 255, 255))
    img = pop_in(img, layer, min(1.0, lt / 8.0))
    return vignette(img)


def scene_landing(t):
    """16-22s: touchdown on the yacht deck, splash, disbelief."""
    lt = t - 16.0
    img = sky_dusk().convert("RGBA")
    dr = ImageDraw.Draw(img, "RGBA")
    draw_stars(dr, t)
    sun(dr, 540, 500, 64)
    skyline(dr, 900, (40, 20, 66), seed=31)
    water(dr, 900, t)
    yx = 700.0
    deck_y = yacht(dr, yx, 1480, 1.05, t)
    car(dr, yx + 190, 1400, 1.05, 0.0)
    splash(dr, yx + 40, 1560, min(1.0, lt / 1.6), s=0.62)
    img = img.convert("RGB")
    img = shake(img, t, 16.0, 0.45, amp=16)
    layer, ldr = text_layer()
    if lt > 0.35:
        draw_text(ldr, W // 2, 300, "HE ACTUALLY", 132, fill=(255, 255, 255))
        draw_text(ldr, W // 2, 450, "LANDED IT!", 150, fill=(80, 255, 140))
    if lt > 2.6:
        draw_text(ldr, W // 2, 700, "VICE CITY WILL NEVER", 64,
                  fill=(255, 255, 255))
        draw_text(ldr, W // 2, 780, "BE THE SAME", 64, fill=(255, 255, 255))
    img = pop_in(img, layer, min(1.0, max(0.0, lt - 0.35) / 5.0))
    return vignette(img)


def scene_pitch(t):
    """22-30s: make.fun pitch on a clean dark card."""
    lt = t - 22.0
    img = vgrad((10, 14, 26), (16, 60, 44)).convert("RGBA")
    dr = ImageDraw.Draw(img, "RGBA")
    # subtle rising bars (equaliser feel)
    for k in range(24):
        bh = 60 + 130 * abs(math.sin(t * 2.2 + k * 0.7))
        x = 40 + k * 43
        dr.rectangle([x, 1780 - bh, x + 22, 1780],
                     fill=(34, 197, 94, 70))
    # green accent line
    dr.rectangle([140, 500, 940, 512], fill=(34, 197, 94, 255))
    img = img.convert("RGB")
    layer, ldr = text_layer()
    draw_text(ldr, W // 2, 330, "GTA 6  •  VICE CITY", 52,
              fill=(255, 214, 80))
    if lt > 0.2:
        draw_text(ldr, W // 2, 560, "MAKE CLIPS LIKE THIS", 88,
                  fill=(255, 255, 255))
        draw_text(ldr, W // 2, 670, "WITH AI", 88, fill=(255, 255, 255))
    if lt > 2.4:
        draw_text(ldr, W // 2, 830, "AND EARN MONEY ON", 72,
                  fill=(255, 255, 255))
        draw_text(ldr, W // 2, 920, "make.fun", 150, fill=(34, 197, 94))
    if lt > 4.6:
        draw_text(ldr, W // 2, 1220, "make.fun/bounty/gta6-clipper-01", 46,
                  fill=(255, 255, 255))
    if lt > 5.6:
        draw_text(ldr, W // 2, 1340, "PLAY CODE: makefun-runway-trail-snail",
                  42, fill=(255, 214, 80))
    img = pop_in(img, layer, min(1.0, lt / 8.0))
    return vignette(img)


def frame_at(t):
    if t < 3.0:
        return scene_hook(t)
    if t < 8.0:
        return scene_reveal(t)
    if t < 16.0:
        return scene_air(t)
    if t < 22.0:
        return scene_landing(t)
    return scene_pitch(t)


# ---------------------------------------------------------------- audio
def synth_audio(path):
    n = int(DUR * SR)
    t = np.arange(n, dtype=np.float64) / SR
    mix = np.zeros(n)
    bpm = 128.0
    beat = 60.0 / bpm

    def add(sig, lo, hi):
        i0, i1 = int(lo * SR), min(n, int(hi * SR))
        if i1 > i0:
            mix[i0:i1] += sig[: i1 - i0]

    # kick on every beat
    for b in range(int(DUR / beat)):
        s0 = b * beat
        ln = int(0.26 * SR)
        tt = np.arange(ln) / SR
        f = 130 * np.exp(-tt * 22) + 46
        ph = 2 * np.pi * np.cumsum(f) / SR
        add(np.sin(ph) * np.exp(-tt * 13) * 0.9, s0, s0 + 0.26)
    # hats on offbeats
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n)
    for b in range(int(DUR / beat)):
        s0 = b * beat + beat / 2
        ln = int(0.05 * SR)
        seg = np.diff(noise[int(s0 * SR): int(s0 * SR) + ln], prepend=0)
        add(seg * np.exp(-np.arange(len(seg)) / SR * 90) * 0.20, s0, s0 + 0.05)
    # bass: A1 A1 C2 E2 per bar
    bass_notes = [55.0, 55.0, 65.41, 82.41]
    for bar in range(int(DUR / (beat * 4))):
        for k, f0 in enumerate(bass_notes):
            s0 = bar * beat * 4 + k * beat
            ln = int(0.42 * SR)
            tt = np.arange(ln) / SR
            add((np.sin(2 * np.pi * f0 * tt) + 0.4 * np.sin(4 * np.pi * f0 * tt))
                * np.exp(-tt * 5) * 0.34, s0, s0 + 0.42)
    # arp 16ths, quiet
    arp = [220.0, 261.63, 329.63, 440.0, 329.63, 261.63]
    for i in range(int(DUR / (beat / 4))):
        s0 = i * beat / 4
        f0 = arp[i % len(arp)]
        ln = int(0.10 * SR)
        tt = np.arange(ln) / SR
        add(np.sin(2 * np.pi * f0 * tt) * np.exp(-tt * 30) * 0.10, s0, s0 + 0.10)
    # pad
    add((np.sin(2 * np.pi * 110 * t) + np.sin(2 * np.pi * 164.81 * t)) * 0.05,
        0, DUR)
    # engine rev 3-8s: rising saw-ish sweep
    ln = int(5 * SR)
    tt = np.arange(ln) / SR
    f0 = 70 + 190 * (tt / 5) ** 2
    ph = 2 * np.pi * np.cumsum(f0) / SR
    add((np.sin(ph) + 0.5 * np.sin(2 * ph)) * (0.10 + 0.22 * tt / 5), 3.0, 8.0)
    # wind whoosh 8-16s: shaped noise
    ln = int(8 * SR)
    seg = noise[int(8 * SR): int(8 * SR) + ln]
    env = np.sin(np.linspace(0, np.pi, ln)) ** 2
    add(np.convolve(seg, np.ones(400) / 400, mode="same") * env * 0.30, 8.0, 16.0)
    # impact boom at 16.0s
    ln = int(0.7 * SR)
    tt = np.arange(ln) / SR
    add(np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 9) * 0.95, 16.0, 16.7)
    add(noise[int(16 * SR): int(16 * SR) + ln] * np.exp(-tt * 14) * 0.35,
        16.0, 16.7)
    # splash 16.1-17.2s
    ln = int(1.1 * SR)
    seg = noise[int(16.1 * SR): int(16.1 * SR) + ln]
    add(np.convolve(seg, np.ones(900) / 900, mode="same")
        * np.exp(-np.arange(ln) / SR * 3.2) * 0.30, 16.1, 17.2)
    # cheer swell 16.5-20s
    ln = int(3.5 * SR)
    seg = noise[int(16.5 * SR): int(16.5 * SR) + ln]
    env = np.sin(np.linspace(0, np.pi, ln))
    add(np.convolve(seg, np.ones(1500) / 1500, mode="same") * env * 0.16,
        16.5, 20.0)

    mix = np.tanh(mix * 1.1)
    peak = np.max(np.abs(mix))
    mix = mix / peak * 0.89
    stereo = np.stack([mix, mix], axis=1)
    pcm = (stereo * 32767).astype(np.int16)
    import wave
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- main
def main():
    out = sys.argv[1]
    wav = out + ".wav"
    print("synthesising audio ...", flush=True)
    synth_audio(wav)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
        "-r", str(FPS), "-i", "pipe:0",
        "-i", wav,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-threads", "1",
        "-video_track_timescale", "30",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-metadata", "creation_time=2026-11-22T00:00:00.000Z",
        "-movflags", "+faststart",
        "-t", str(DUR),
        out,
    ]
    print("encoding ...", flush=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(NFRAMES):
        t = i / FPS
        frame = frame_at(t)
        proc.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
        if i % 150 == 0:
            print(f"  frame {i}/{NFRAMES} t={t:.1f}s", flush=True)
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        sys.exit(f"ffmpeg failed rc={proc.returncode}")
    print("done:", out, flush=True)


if __name__ == "__main__":
    main()
