#!/usr/bin/env python3
"""Render a talking-head clip into an Ali Abdaal-style 9:16 short.

Usage:
    python3 video/render.py <source.mov> video/projects/<name>/edit.json [out_dir]

The edit spec lists the source ranges to keep (jump cuts), the caption text
for each range ("|" splits caption chunks, *word* highlights, [key=value]
tags trigger on-screen graphics), plus the title / stage / outro cards.
"""
import json
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
ACCENT = (255, 196, 0)
WHITE = (255, 255, 255)
INK = (20, 20, 24)
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
# Face position in the source frame; zoom crops are centred here.
ANCHOR = (0.47, 0.58)
# TikTok UI safe zone: keep text between these y values and away from the right rail.
SAFE_TOP, CAPTION_Y, MARGIN = 190, 1420, 80

_fonts = {}


def font(weight, size):
    key = (weight, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(os.path.join(FONT_DIR, f"Inter-{weight}.ttf"), size)
    return _fonts[key]


# ---------------------------------------------------------------- spec parsing

def parse_chunks(text):
    """'a *b*[k=v]|c' -> [{'words': [(w, hi)], 'tags': {k: v}, 'plain': str}]"""
    chunks = []
    for raw in text.split("|"):
        tags = dict(re.findall(r"\[(\w+)=([^\]]+)\]", raw))
        body = re.sub(r"\[\w+=[^\]]+\]", "", raw).strip()
        words = []
        for part in re.split(r"(\*[^*]+\*)", body):
            hi = part.startswith("*")
            for w in part.strip("*").split():
                # Captions read cleaner without trailing commas/full stops.
                w = w.rstrip(".,")
                if w:
                    words.append((w, hi))
        chunks.append({"words": words, "tags": tags, "plain": " ".join(w for w, _ in words)})
    return chunks


def loudness_envelope(src):
    """Per-10ms loudness (dB) of the source audio, used to time captions to speech."""
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        check=True, capture_output=True).stdout
    a = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    hop = 160
    n = len(a) // hop
    rms = np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-10)
    return 20 * np.log10(rms)


def build_timeline(spec, env):
    """Map every caption chunk to output-time [start, end), weighting by voiced time."""
    events, t_out = [], 0.0
    for seg in spec["segments"]:
        seg["t0"] = t_out
        dur = seg["out"] - seg["in"]
        chunks = parse_chunks(seg["text"])
        lo, hi = int(seg["in"] * 100), int(seg["out"] * 100)
        voiced = (env[lo:hi] > env[lo:hi].max() - 30).astype(float)
        cum = np.concatenate([[0], np.cumsum(voiced)])
        cum /= cum[-1] or 1
        weights = np.array([len(c["plain"]) + 4 for c in chunks], float)
        bounds = np.concatenate([[0], np.cumsum(weights) / weights.sum()])
        # Fraction of characters spoken -> fraction of voiced frames -> seconds.
        times = [np.searchsorted(cum, b) / 100 for b in bounds]
        times[0], times[-1] = 0.0, dur
        for c, a, b in zip(chunks, times, times[1:]):
            c["start"], c["end"] = t_out + a, t_out + b
            events.append(c)
        t_out += dur
    return events, t_out


# ---------------------------------------------------------------- drawing

def pill(d, x, y, text, fnt, fill, fg, pad=(30, 16)):
    b = d.textbbox((0, 0), text, font=fnt)
    w, h = b[2] - b[0] + 2 * pad[0], b[3] - b[1] + 2 * pad[1]
    d.rounded_rectangle([x, y, x + w, y + h], h // 2, fill=fill)
    d.text((x + pad[0] - b[0], y + pad[1] - b[1]), text, font=fnt, fill=fg)
    return w, h


def top_shade(img, height=620, alpha=120):
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([0, 0, W, height], fill=(0, 0, 0, alpha))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(70)))


def caption_layer(words):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 80
    f = font("Black", size)
    space = d.textlength(" ", font=f)
    # Greedy wrap into lines no wider than the safe area.
    lines, cur, cur_w = [], [], 0
    for w, hi in words:
        ww = d.textlength(w, font=f)
        if cur and cur_w + space + ww > W - 2 * MARGIN:
            lines.append((cur, cur_w))
            cur, cur_w = [], 0
        cur_w += (space if cur else 0) + ww
        cur.append((w, hi, ww))
    if cur:
        lines.append((cur, cur_w))
    line_h = int(size * 1.18)
    y = CAPTION_Y - line_h * (len(lines) - 1) // 2
    for line, lw in lines:
        x = (W - lw) / 2
        for w, hi, ww in line:
            d.text((x, y), w, font=f, fill=ACCENT if hi else WHITE,
                   stroke_width=8, stroke_fill=(0, 0, 0), anchor="ls")
            x += ww + space
        y += line_h
    return img


def title_layer(t):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    top_shade(img)
    d = ImageDraw.Draw(img)
    pill(d, MARGIN, SAFE_TOP, t["kicker"], font("Bold", 36), ACCENT + (255,), INK)
    d.text((MARGIN, SAFE_TOP + 100), t["line1"], font=font("Black", 108), fill=WHITE)
    d.text((MARGIN, SAFE_TOP + 220), t["line2"], font=font("Black", 108), fill=ACCENT)
    return img


def list_layer(names, active):
    """Numbered list card; items up to `active` are revealed, `active` is highlighted."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, row = MARGIN, SAFE_TOP, 92
    d.rounded_rectangle([x0, y0, x0 + 660, y0 + 40 + row * len(names)], 40, fill=(255, 255, 255, 236))
    for i, n in enumerate(names):
        y = y0 + 32 + i * row
        on, seen = i + 1 == active, i + 1 <= active
        d.ellipse([x0 + 34, y, x0 + 96, y + 62], fill=ACCENT if on else (232, 232, 236))
        num = str(i + 1)
        f = font("Black", 34)
        b = d.textbbox((0, 0), num, font=f)
        d.text((x0 + 65 - (b[0] + b[2]) / 2, y + 31 - (b[1] + b[3]) / 2), num, font=f, fill=INK)
        colour = INK if on else ((70, 70, 78) if seen else (170, 170, 178))
        d.text((x0 + 124, y + 6), n, font=font("Black" if on else "SemiBold", 44), fill=colour)
    return img


def stage_layer(stages, n):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    top_shade(img, 520, 100)
    d = ImageDraw.Draw(img)
    st = stages[n - 1]
    w, h = pill(d, MARGIN, SAFE_TOP, f"#{n}", font("Black", 54), ACCENT + (255,), INK, pad=(26, 16))
    pill(d, MARGIN + w + 14, SAFE_TOP, st["name"], font("Black", 54), (255, 255, 255, 246), INK)
    d.text((MARGIN + 4, SAFE_TOP + h + 26), st["sub"], font=font("Bold", 40), fill=WHITE,
           stroke_width=3, stroke_fill=(0, 0, 0))
    # Five-segment progress indicator.
    seg_w, gap, y = 120, 12, SAFE_TOP + h + 100
    for i in range(5):
        x = MARGIN + i * (seg_w + gap)
        d.rounded_rectangle([x, y, x + seg_w, y + 12], 6,
                            fill=ACCENT + (255,) if i < n else (255, 255, 255, 110))
    return img


def outro_layer(o, part):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    top_shade(img)
    d = ImageDraw.Draw(img)
    pill(d, MARGIN, SAFE_TOP, o["kicker"], font("Bold", 36), ACCENT + (255,), INK)
    d.text((MARGIN, SAFE_TOP + 100), o["line1"], font=font("Black", 96), fill=WHITE)
    d.text((MARGIN, SAFE_TOP + 205), o["line2"], font=font("Black", 96), fill=ACCENT)
    if part >= 2:
        pill(d, MARGIN, SAFE_TOP + 350, o["cta"], font("Black", 46), (255, 255, 255, 246), INK)
    return img


def with_alpha(img, k):
    if k >= 1:
        return img
    out = img.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * k)))
    return out


# ---------------------------------------------------------------- pipeline

def cut_filters(spec):
    v, a = [], []
    for i, s in enumerate(spec["segments"]):
        dur = s["out"] - s["in"]
        v.append(f"[0:v]trim={s['in']}:{s['out']},setpts=PTS-STARTPTS,fps={FPS}[v{i}]")
        a.append(f"[0:a]atrim={s['in']}:{s['out']},asetpts=PTS-STARTPTS,"
                 f"afade=t=in:d=0.02,afade=t=out:st={dur - 0.03:.3f}:d=0.03[a{i}]")
    n = len(spec["segments"])
    video = ";".join(v) + ";" + "".join(f"[v{i}]" for i in range(n)) + \
        f"concat=n={n}:v=1:a=0,eq=brightness=0.04:contrast=1.06:saturation=1.08," \
        "colorbalance=rs=0.03:bs=-0.03,format=rgb24[v]"
    audio = ";".join(a) + ";" + "".join(f"[a{i}]" for i in range(n)) + \
        f"concat=n={n}:v=0:a=1,highpass=f=80,afftdn=nf=-25," \
        "acompressor=threshold=-20dB:ratio=3:attack=5:release=80," \
        "loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    return video, audio


def frame_state(t, events, spec):
    """Which caption / card is on screen at output time t, and since when."""
    cap, state = None, {"card": ("title",), "since": 0.0}
    for e in events:
        if e["start"] > t:
            break
        cap = e
        tags = e["tags"]
        if "list" in tags:
            state = {"card": ("list", int(tags["list"])), "since": e["start"]}
        elif "stage" in tags:
            state = {"card": ("stage", int(tags["stage"])), "since": e["start"]}
        elif "outro" in tags:
            state = {"card": ("outro", int(tags["outro"])), "since": e["start"]}
    return cap, state


def card_layer(card, spec, cache):
    if card not in cache:
        kind = card[0]
        if kind == "title":
            cache[card] = title_layer(spec["title"])
        elif kind == "list":
            cache[card] = list_layer(spec["list"], card[1])
        elif kind == "stage":
            cache[card] = stage_layer(spec["stages"], card[1])
        else:
            cache[card] = outro_layer(spec["outro"], card[1])
    return cache[card]


def main():
    src, spec_path = sys.argv[1], sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(spec_path), "out")
    os.makedirs(out_dir, exist_ok=True)
    spec = json.load(open(spec_path))
    events, total = build_timeline(spec, loudness_envelope(src))

    vf, af = cut_filters(spec)
    audio_path = os.path.join(out_dir, "audio.m4a")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-filter_complex", af, "-map", "[a]",
                    "-ar", "48000", "-c:a", "aac", "-b:a", "192k", audio_path], check=True)

    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", src],
                           check=True, capture_output=True, text=True).stdout.strip().split(",")
    sw, sh = int(probe[0]), int(probe[1])
    reader = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-filter_complex", vf, "-map", "[v]",
                               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    video_path = os.path.join(out_dir, "tiktok.mp4")
    writer = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", audio_path,
                               "-vf", "unsharp=5:5:0.5", "-c:v", "libx264", "-preset", "slow",
                               "-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "high",
                               "-c:a", "copy", "-shortest", "-movflags", "+faststart", video_path],
                              stdin=subprocess.PIPE)

    segs = spec["segments"]
    cards, captions = {}, {}
    fade = 0.2
    i = 0
    while True:
        buf = reader.stdout.read(sw * sh * 3)
        if len(buf) < sw * sh * 3:
            break
        t = i / FPS
        seg = next((s for s in reversed(segs) if s["t0"] <= t), segs[0])
        p = min(1.0, (t - seg["t0"]) / max(0.1, seg["out"] - seg["in"]))
        z = seg.get("zoom", 1.0) * (1 + 0.03 * p)  # slow push-in within each cut
        cw, ch = sw / z, sh / z
        cx = min(max(ANCHOR[0] * sw, cw / 2), sw - cw / 2)
        cy = min(max(ANCHOR[1] * sh, ch / 2), sh - ch / 2)
        frame = Image.frombuffer("RGB", (sw, sh), buf).resize(
            (W, H), Image.LANCZOS, box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)).convert("RGBA")

        cap, state = frame_state(t, events, spec)
        frame.alpha_composite(with_alpha(card_layer(state["card"], spec, cards),
                                         (t - state["since"]) / fade if state["since"] else 1))
        if cap is not None:
            key = id(cap)
            if key not in captions:
                captions[key] = caption_layer(cap["words"])
            frame.alpha_composite(captions[key])
        writer.stdin.write(frame.convert("RGB").tobytes())
        if i == int(1.2 * FPS):
            frame.convert("RGB").save(os.path.join(out_dir, "preview_hook.jpg"), quality=88)
        i += 1
    writer.stdin.close()
    writer.wait()
    reader.wait()

    write_srt(events, os.path.join(out_dir, "captions.srt"))
    write_cover(src, spec, os.path.join(out_dir, "cover.jpg"))
    print(f"rendered {i} frames ({i / FPS:.1f}s, planned {total:.1f}s) -> {video_path}")


def write_srt(events, path):
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"
    with open(path, "w") as f:
        for n, e in enumerate(events, 1):
            f.write(f"{n}\n{ts(e['start'])} --> {ts(e['end'])}\n{e['plain']}\n\n")


def write_cover(src, spec, path):
    t = spec.get("cover_time", 12.0)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", src, "-frames:v", "1",
                          "-vf", f"scale={W}:{H}:flags=lanczos,eq=brightness=0.04:contrast=1.06:saturation=1.08",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
    img = Image.frombuffer("RGB", (W, H), raw).convert("RGBA")
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle([0, 0, W, 900], fill=(0, 0, 0, 150))
    img.alpha_composite(shade.filter(ImageFilter.GaussianBlur(90)))
    d = ImageDraw.Draw(img)
    pill(d, MARGIN, 300, spec["title"]["kicker"], font("Bold", 40), ACCENT + (255,), INK)
    d.text((MARGIN, 410), "5 STAGES", font=font("Black", 150), fill=WHITE)
    d.text((MARGIN, 570), "OF AWARENESS", font=font("Black", 112), fill=ACCENT)
    pill(d, MARGIN, 730, "Bukan TOFU MOFU BOFU je", font("Black", 50), (255, 255, 255, 246), INK)
    img.convert("RGB").save(path, quality=92)


if __name__ == "__main__":
    main()
