#!/usr/bin/env python3
"""Render a voiceover (e.g. ElevenLabs) into a faceless Ali Abdaal-style 9:16 short.

Usage:
    python3 video/faceless.py video/projects/<name>/edit.json [out_dir]

Instead of a camera take, every frame is drawn: a paper/grid background, a scene
card in the middle (title, paper-cut animation, badges, steps, CTA), a stage
header with progress bar, and word-by-word captions timed from a transcript.

The spec's "script" uses the same chunk syntax as render.py ("|" splits caption
chunks, *word* highlights). Tags trigger changes from that chunk on:
    [scene=key]  switch the middle card      [stage=n]  stage header (0 hides it)
    [reveal=n]   show the first n items of a badges/steps card
    [sfx=name]   play a sound effect
Caption chunks are timed by matching their words to the transcript in "words"
(a list of {"text", "start", "end"}), so the spoken text may differ slightly
from what is shown (e.g. "mindsel dot my" is shown as "mindsel.my").
"""
import difflib
import json
import math
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from render import FPS, H, MARGIN, SAFE_TOP, W, emoji, fit, font, parse_chunks, pill, with_alpha, write_srt

# Mindsel brand palette (from mindsel.my).
CREAM = (250, 249, 246)
TEAL = (13, 92, 117)
DEEP = (0, 67, 87)
ORANGE = (217, 119, 54)
MINT = (192, 236, 221)
INK = (24, 38, 44)
FAINT = (24, 38, 44, 70)

VIS_Y0, VIS_Y1 = 470, 1230   # middle card area
CAPTION_Y = 1400
FADE = 0.28


def label_font(size):
    """Nitti (from the AA asset pack) for small labels, Inter Bold as fallback."""
    path = os.path.join(ASSET_DIR, "Fonts", "Nitti-Bold.ttf")
    return ImageFont.truetype(path, size) if os.path.exists(path) else font("Bold", size)


def asset(*parts):
    path = os.path.join(ASSET_DIR, *parts)
    return path if os.path.exists(path) else None


# ---------------------------------------------------------------- timing

def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def load_words(path):
    data = json.load(open(path))
    words = data.get("words", data) if isinstance(data, dict) else data
    return [w for w in words if norm(w.get("text", "")) and w.get("type", "word") == "word"]


def build_timeline(spec, words, base_dir):
    """Time every caption chunk (and each word in it) against the transcript."""
    chunks = parse_chunks(spec["script"])
    for c in chunks:  # glue stray punctuation ("…", "?") onto the word before it
        merged = []
        for w, hi in c["words"]:
            if not norm(w) and merged:
                merged[-1] = (merged[-1][0] + w, merged[-1][1])
            elif norm(w):
                merged.append((w, hi))
        c["words"] = merged
    flat = [(ci, wi, norm(w)) for ci, c in enumerate(chunks) for wi, (w, _) in enumerate(c["words"])]
    said = [norm(w["text"]) for w in words]
    match = {}
    sm = difflib.SequenceMatcher(None, [f[2] for f in flat], said, autojunk=False)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            match[a + k] = b + k
    # Unmatched script words: interpolate between the neighbouring matched ones.
    starts, ends = [], []
    known = sorted(match)
    for i in range(len(flat)):
        if i in match:
            starts.append(words[match[i]]["start"])
            ends.append(words[match[i]]["end"])
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        t0 = words[match[prev]]["end"] if prev is not None else 0.0
        t1 = words[match[nxt]]["start"] if nxt is not None else words[-1]["end"]
        span_lo = prev if prev is not None else -1
        span_hi = nxt if nxt is not None else len(flat)
        f = (i - span_lo) / (span_hi - span_lo)
        starts.append(t0 + (t1 - t0) * f)
        ends.append(t0 + (t1 - t0) * f + 0.15)
    pos = 0
    for c in chunks:
        n = len(c["words"])
        c["word_t"] = starts[pos:pos + n]
        if n:
            c["start"], c["last_end"] = starts[pos], ends[pos + n - 1]
        else:  # an empty chunk (e.g. a closing card) starts just after the voice
            c["start"] = c["last_end"] = (ends[pos - 1] if pos else 0.0) + spec.get("gap", 0.6)
        pos += n
    chunks[0]["start"] = 0.0
    for c, nxt in zip(chunks, chunks[1:]):
        c["end"] = nxt["start"]
    total = max(words[-1]["end"], chunks[-1]["start"]) + spec.get("tail", 2.5)
    chunks[-1]["end"] = total
    return chunks, total


# ---------------------------------------------------------------- background

def make_background():
    """Cream paper with a soft grid, taller than the frame so it can drift."""
    bg = Image.new("RGB", (W, H + 120), CREAM)
    grid = asset("Assets", "Grid BG (1).jpg")
    if grid:
        g = Image.open(grid).convert("L").resize((W, H + 120), Image.LANCZOS)
        # Keep only the grid lines, tinted mint-teal, at low strength.
        lines = np.asarray(g, np.float32)
        lines = np.clip((lines - np.median(lines)) / 18, 0, 1)
        arr = np.asarray(bg, np.float32)
        tint = np.array(TEAL, np.float32)
        arr = arr * (1 - 0.16 * lines[..., None]) + tint * 0.16 * lines[..., None]
        bg = Image.fromarray(arr.astype(np.uint8))
    else:
        d = ImageDraw.Draw(bg)
        for x in range(0, W, 60):
            d.line([(x, 0), (x, H + 120)], fill=(226, 236, 233), width=2)
        for y in range(0, H + 120, 60):
            d.line([(0, y), (W, y)], fill=(226, 236, 233), width=2)
    paper = asset("Assets", "Paper Folds.jpg")
    if paper:
        p = Image.open(paper).convert("L").resize(bg.size, Image.LANCZOS)
        fine = np.asarray(p.filter(ImageFilter.GaussianBlur(2)), np.float32)
        broad = np.asarray(p.filter(ImageFilter.GaussianBlur(40)), np.float32)
        p = 1 + 0.9 * ((fine - broad) / 255).clip(-0.15, 0.15)  # crinkle texture only
        bg = Image.fromarray((np.asarray(bg, np.float32) * p[..., None]).clip(0, 255).astype(np.uint8))
    return np.asarray(bg)


# ---------------------------------------------------------------- card pieces

_tape_cache = {}


def tape(img, x, y, angle):
    """A strip of masking tape (asset if available, else drawn) centred at x, y."""
    src = asset("Assets", "Masking Tape01.jpeg")
    if src:
        t = _tape_cache.get(src)
        if t is None:
            g = Image.open(src).convert("L")
            g.thumbnail((600, 600))
            a = g.point(lambda v: max(0, min(255, (v - 60) * 3)))
            box = a.point(lambda v: 255 if v > 128 else 0).getbbox()
            tint = Image.new("RGB", g.size, (240, 232, 205))
            t = Image.merge("RGBA", (*tint.split(), a.point(lambda v: int(v * 0.85)))).crop(box)
            t = t.resize((230, max(1, int(230 * t.height / t.width))), Image.LANCZOS)
            _tape_cache[src] = t
    else:
        t = Image.new("RGBA", (220, 64), (236, 224, 190, 205))
    t = t.rotate(angle, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(t, (int(x - t.width / 2), int(y - t.height / 2)))


def paper_card(img, box, radius=26, tapes=True):
    x0, y0, x1, y1 = box
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0 + 6, y0 + 16, x1 + 6, y1 + 16], radius, fill=(0, 40, 50, 60))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
    ImageDraw.Draw(img).rounded_rectangle(box, radius, fill=(255, 255, 255, 255))
    if tapes:
        tape(img, x0 + 40, y0 + 4, 28)
        tape(img, x1 - 40, y0 + 4, -24)


def centered(d, cx, y, text, fnt, fill, anchor="mm"):
    d.text((cx, y), text, font=fnt, fill=fill, anchor=anchor)


def scene_layer(sc, reveal):
    """Static drawing of a scene card; clip frames are added per frame on top."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    kind = sc["type"]
    cx = W // 2
    if kind == "hero":
        y = 640
        if sc.get("kicker"):
            f = label_font(50)
            tw = d.textlength(sc["kicker"], font=f)
            pill(d, int(cx - tw / 2 - 30), y - 150, sc["kicker"], f, ORANGE + (255,), (255, 255, 255))
        if sc.get("emoji"):
            e = emoji(sc["emoji"], 170)
            img.alpha_composite(e, (cx - e.width // 2, y - 30))
            y += 200
        centered(d, cx, y + 40, sc["line1"], fit(sc["line1"], "Black", 120), DEEP)
        if sc.get("line2"):
            centered(d, cx, y + 175, sc["line2"], fit(sc["line2"], "Black", 120), ORANGE)
        if sc.get("sub"):
            centered(d, cx, y + 290, sc["sub"], fit(sc["sub"], "Bold", 60), TEAL)
    elif kind == "strike":
        f = fit(sc["text"], "Black", 130)
        centered(d, cx, 700, f'"{sc["text"]}"', f, DEEP)
        if reveal >= 1:
            tw = d.textlength(f'"{sc["text"]}"', font=f)
            d.line([(cx - tw / 2 - 10, 712), (cx + tw / 2 + 10, 688)], fill=ORANGE, width=16)
            centered(d, cx, 900, sc["after"], fit(sc["after"], "Black", 130), ORANGE)
    elif kind in ("anim", "card"):
        bw, bh = 760, 700
        box = [cx - bw // 2, VIS_Y0 + 20, cx + bw // 2, VIS_Y0 + 20 + bh]
        paper_card(img, box)
        if not sc.get("clip_path") and sc.get("emoji"):
            e = emoji(sc["emoji"], 260)
            img.alpha_composite(e, (cx - e.width // 2, box[1] + 90))
        centered(d, cx, box[1] + 520, sc["title"], fit(sc["title"], "Black", 78, bw - 80), DEEP)
        if sc.get("sub"):
            centered(d, cx, box[1] + 610, sc["sub"], fit(sc["sub"], "Bold", 40, bw - 80), TEAL)
    elif kind in ("badges", "steps"):
        items = sc["items"]
        row = 150 if kind == "badges" else 165
        y0 = (VIS_Y0 + VIS_Y1) // 2 - row * len(items) // 2
        for i, it in enumerate(items):
            if i >= reveal:
                break
            y = y0 + i * row
            box = [MARGIN + 20, y, W - MARGIN - 20, y + row - 26]
            paper_card(img, box, 24, tapes=False)
            d.rectangle([box[0], box[1] + 18, box[0] + 12, box[3] - 18], fill=ORANGE if kind == "steps" else TEAL)
            if kind == "badges":
                e = emoji(it[0], 76)
                img.alpha_composite(e, (box[0] + 40, (box[1] + box[3]) // 2 - e.height // 2))
                d.text((box[0] + 150, (box[1] + box[3]) / 2), it[1], font=fit(it[1], "Black", 54, 640),
                       fill=DEEP, anchor="lm")
            else:
                d.text((box[0] + 44, (box[1] + box[3]) / 2), it[0], font=label_font(56), fill=ORANGE, anchor="lm")
                d.text((box[0] + 150, box[1] + 30), it[1], font=fit(it[1], "Black", 52, 640), fill=DEEP)
                if len(it) > 2:
                    d.text((box[0] + 150, box[1] + 92), it[2], font=fit(it[2], "SemiBold", 34, 640), fill=TEAL)
    elif kind == "cta":
        bw, bh = 860, 620
        box = [cx - bw // 2, VIS_Y0 + 40, cx + bw // 2, VIS_Y0 + 40 + bh]
        paper_card(img, box)
        f = label_font(48)
        tw = d.textlength(sc["kicker"], font=f)
        pill(d, int(cx - tw / 2 - 30), box[1] + 70, sc["kicker"], f, ORANGE + (255,), (255, 255, 255))
        centered(d, cx, box[1] + 250, sc["title"], fit(sc["title"], "Black", 96, bw - 80), DEEP)
        url_f = fit(sc["url"], "Black", 84, bw - 120)
        uw = d.textlength(sc["url"], font=url_f)
        d.rounded_rectangle([cx - uw / 2 - 36, box[1] + 330, cx + uw / 2 + 36, box[1] + 450], 60, fill=TEAL)
        centered(d, cx, box[1] + 390, sc["url"], url_f, (255, 255, 255))
        if sc.get("pills"):
            text = "  ·  ".join(sc["pills"])
            centered(d, cx, box[1] + 530, text, fit(text, "Bold", 42, bw - 80), TEAL)
    elif kind == "end":
        d.rectangle([0, 0, W, H], fill=DEEP + (255,))
        centered(d, cx, 760, sc["brand"], fit(sc["brand"], "Black", 150), (255, 255, 255))
        centered(d, cx, 880, sc["tagline"], fit(sc["tagline"], "Bold", 64), MINT)
        url_f = font("Black", 64)
        uw = d.textlength(sc["url"], font=url_f)
        d.rounded_rectangle([cx - uw / 2 - 40, 990, cx + uw / 2 + 40, 1100], 56, fill=ORANGE)
        centered(d, cx, 1045, sc["url"], url_f, (255, 255, 255))
    if sc.get("footer"):
        dark = kind == "end"
        centered(d, cx, 1250 if dark else VIS_Y1 - 40, sc["footer"], fit(sc["footer"], "SemiBold", 32),
                 MINT if dark else TEAL)
    return img


def load_clip(path, size, max_secs=4.0):
    """Decode a green/blue-screen paper-cut clip into keyed RGBA frames.

    The key colour is sampled from the frame border, spill is pulled out of the
    edges, and every frame is cropped to the union of the object's extent so the
    object fills `size`.
    """
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", path],
                           check=True, capture_output=True, text=True).stdout.strip().split(",")
    sw, sh = int(probe[0]), int(probe[1])
    w = 720
    h = int(sh * w / sw) // 2 * 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-t", str(max_secs), "-i", path, "-vf",
                          f"fps={FPS},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         check=True, capture_output=True).stdout
    rgb = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3).astype(np.float32)
    border = np.concatenate([rgb[0, :8].reshape(-1, 3), rgb[0, -8:].reshape(-1, 3),
                             rgb[0, :, :8].reshape(-1, 3), rgb[0, :, -8:].reshape(-1, 3)])
    key = np.median(border, axis=0)
    dist = np.sqrt(((rgb - key) ** 2).sum(-1))
    alpha = np.clip((dist - 70) / 90, 0, 1)
    ch = int(np.argmax(key))  # dominant channel of the key (1 = green, 2 = blue)
    others = [c for c in range(3) if c != ch]
    rgb[..., ch] = np.minimum(rgb[..., ch], np.maximum(rgb[..., others[0]], rgb[..., others[1]]))
    ys, xs = np.nonzero((alpha > 0.5).any(axis=0))
    pad = 12
    y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + pad)
    x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + pad)
    k = min(size[0] / (x1 - x0), size[1] / (y1 - y0))
    out_size = (max(1, int((x1 - x0) * k)), max(1, int((y1 - y0) * k)))
    frames = []
    for f, a in zip(rgb, alpha):
        img = np.dstack([f[y0:y1, x0:x1], a[y0:y1, x0:x1, None] * 255]).astype(np.uint8)
        frames.append(Image.fromarray(img, "RGBA").resize(out_size, Image.LANCZOS))
    return frames


def clip_frame(frames, t):
    """Play the unfold-in once, then rock back and forth through the 'held' middle."""
    n = len(frames)
    i = int(t * FPS)
    lo, hi = int(n * 0.3), max(int(n * 0.6), int(n * 0.3) + 2)
    if i < hi:
        return frames[i]
    span = hi - lo
    j = (i - hi) % (2 * span)
    return frames[hi - 1 - j] if j < span else frames[lo + (j - span)]


# ---------------------------------------------------------------- overlays

def stage_layer(stages, n):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    st = stages[n - 1]
    f = font("Black", 50)
    w, h = pill(d, MARGIN, SAFE_TOP, f"{n}/{len(stages)}", f, ORANGE + (255,), (255, 255, 255), pad=(26, 16))
    pill(d, MARGIN + w + 14, SAFE_TOP, st["name"], f, DEEP + (255,), (255, 255, 255))
    gap, y = 12, SAFE_TOP + h + 28
    seg_w = (W - 2 * MARGIN - gap * (len(stages) - 1)) // len(stages)
    for i in range(len(stages)):
        x = MARGIN + i * (seg_w + gap)
        d.rounded_rectangle([x, y, x + seg_w, y + 12], 6, fill=ORANGE if i < n else (210, 222, 220))
    return img


def caption_layer(words, shown):
    """Word-by-word caption: spoken words solid, upcoming ones faint."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = 76
    f = font("Black", size)
    space = d.textlength(" ", font=f)
    lines, cur, cur_w = [], [], 0
    hpad = 14  # room either side of a highlighted word for its marker
    for i, (w, hi) in enumerate(words):
        ww = d.textlength(w, font=f) + (2 * hpad if hi else 0)
        if cur and cur_w + space + ww > W - 2 * MARGIN:
            lines.append((cur, cur_w))
            cur, cur_w = [], 0
        cur_w += (space if cur else 0) + ww
        cur.append((i, w, hi, ww))
    if cur:
        lines.append((cur, cur_w))
    line_h = int(size * 1.2)
    y = CAPTION_Y - line_h * (len(lines) - 1) // 2
    for line, lw in lines:
        x = (W - lw) / 2
        placed = []
        for i, w, hi, ww in line:
            placed.append((i, w, hi, ww, x))
            x += ww + space
        # Consecutive spoken highlighted words share one marker.
        run = None
        for i, w, hi, ww, x in placed + [(None, "", False, 0, 0)]:
            if hi and i is not None and i < shown:
                run = (run[0], x + ww) if run else (x, x + ww)
                continue
            if run:
                d.rounded_rectangle([run[0], y - size * 0.86, run[1], y + size * 0.2], 14, fill=ORANGE)
                run = None
        for i, w, hi, ww, x in placed:
            tx = x + (hpad if hi else 0)
            if i < shown:
                d.text((tx, y), w, font=f, fill=(255, 255, 255) if hi else DEEP, anchor="ls")
            else:
                d.text((tx, y), w, font=f, fill=FAINT, anchor="ls")
        y += line_h
    return img


# ---------------------------------------------------------------- state

def states(chunks):
    """Walk the chunks once and record when each scene / stage / reveal / sfx starts."""
    scene, stage, reveal = None, 0, None
    timeline, sfx = [], []
    for c in chunks:
        tags = c["tags"]
        if "scene" in tags:
            scene, reveal = tags["scene"], None
            scene_t = c["start"]
        if "stage" in tags:
            stage = int(tags["stage"])
        if "reveal" in tags:
            reveal = int(tags["reveal"])
        if "sfx" in tags:
            for name in tags["sfx"].split("+"):
                sfx.append((c["start"], name))
        timeline.append({"t": c["start"], "scene": scene, "scene_t": scene_t, "stage": stage,
                         "reveal": reveal, "chunk": c})
    return timeline, sfx


def mix_audio(spec, voice, sfx, total, out_path):
    inputs, filters, labels = ["-i", voice], [f"[0:a]aresample=48000,apad=whole_dur={total:.2f}[v]"], ["[v]"]
    gains = spec.get("sfx_gain", {})
    files = spec.get("sfx", {})
    k = 1
    for t, name in sfx:
        path = asset("SFX", files.get(name, name))
        if not path:
            continue
        inputs += ["-i", path]
        ms = int(max(0.0, t + spec.get("sfx_offset", {}).get(name, 0.0)) * 1000)
        filters.append(f"[{k}:a]aresample=48000,volume={gains.get(name, 0.35)},adelay={ms}|{ms}[s{k}]")
        labels.append(f"[s{k}]")
        k += 1
    bed = spec.get("bed")
    if bed and asset("SFX", bed["file"]):
        inputs += ["-stream_loop", "-1", "-i", asset("SFX", bed["file"])]
        ms = int(bed.get("from", 0) * 1000)
        filters.append(f"[{k}:a]aresample=48000,volume={bed.get('gain', 0.2)},"
                       f"afade=t=in:d=0.8,adelay={ms}|{ms},atrim=0:{total:.2f}[s{k}]")
        labels.append(f"[s{k}]")
        k += 1
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=first,"
                   f"afade=t=out:st={total - 0.8:.2f}:d=0.8,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[a]", "-ar", "48000", "-c:a", "aac", "-b:a", "192k", out_path], check=True)


def ease(k):
    k = max(0.0, min(1.0, k))
    return 1 - (1 - k) ** 3


def main():
    global ASSET_DIR
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    stills_only = "--stills" in sys.argv  # quick look: save the preview frames, skip encoding
    spec_path = args[0]
    base_dir = os.path.dirname(os.path.abspath(spec_path))
    out_dir = args[1] if len(args) > 1 else os.path.join(base_dir, "out")
    os.makedirs(out_dir, exist_ok=True)
    spec = json.load(open(spec_path))
    ASSET_DIR = os.path.normpath(os.path.join(base_dir, spec.get("assets", "../../assets/aa")))

    words = load_words(os.path.join(base_dir, spec["words"]))
    chunks, total = build_timeline(spec, words, base_dir)
    timeline, sfx = states(chunks)
    # Automatic SFX: a whoosh on every scene change, a pop on every reveal.
    auto = spec.get("auto_sfx", {})
    prev_scene, prev_reveal = None, None
    for st in timeline:
        if st["scene"] != prev_scene and prev_scene is not None and auto.get("scene"):
            sfx.append((st["t"], auto["scene"]))
        if st["reveal"] not in (None, 0, prev_reveal) and auto.get("reveal"):
            sfx.append((st["t"], auto["reveal"]))
        prev_scene, prev_reveal = st["scene"], st["reveal"]

    audio_path = os.path.join(out_dir, "audio.m4a")
    video_path = os.path.join(out_dir, "tiktok.mp4")
    if not stills_only:
        mix_audio(spec, os.path.join(base_dir, spec["voice"]), sfx, total, audio_path)
    writer = None if stills_only else subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", audio_path,
                               "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
                               "-profile:v", "high", "-c:a", "copy", "-shortest", "-movflags", "+faststart",
                               video_path], stdin=subprocess.PIPE)

    bg = make_background()
    scenes = spec["scenes"]
    clip_box = (600, 400)
    for sc in scenes.values():
        clip = sc.get("clip") and asset("Paper Crumple Assets", sc["clip"])
        if clip:
            sc["clip_path"] = clip
            sc["frames"] = load_clip(clip, clip_box)
    scene_cache, stage_cache, cap_cache = {}, {}, {}
    n_frames = int(total * FPS)
    preview_at = {int(t * FPS) for t in spec.get("previews", [])}
    for i in range(n_frames):
        if stills_only and i not in preview_at:
            continue
        t = i / FPS
        st = next(s for s in reversed(timeline) if s["t"] <= t) if t >= timeline[0]["t"] else timeline[0]
        off = int((t * 14) % 120)  # slow upward drift of the grid
        frame = Image.fromarray(bg[off:off + H]).convert("RGBA")

        sc = scenes[st["scene"]]
        reveal = st["reveal"] if st["reveal"] is not None else len(sc.get("items", [])) or 1
        if sc["type"] == "strike":
            reveal = st["reveal"] or 0
        key = (st["scene"], reveal)
        if key not in scene_cache:
            scene_cache[key] = scene_layer(sc, reveal)
        layer = scene_cache[key]
        k = ease((t - st["scene_t"]) / FADE) if st["scene_t"] > 0 else 1.0
        if sc["type"] == "end":
            frame.alpha_composite(with_alpha(layer, k))
        else:
            dy = int(70 * (1 - k))
            frame.alpha_composite(with_alpha(layer, k).crop((0, 0, W, H - dy)), dest=(0, dy))
            if "frames" in sc:
                fr = clip_frame(sc["frames"], t - st["scene_t"])
                fx = W // 2 - fr.width // 2
                fy = VIS_Y0 + 20 + 60 + (clip_box[1] - fr.height) // 2 + dy
                frame.alpha_composite(with_alpha(fr, k), (fx, fy))
        if st["stage"] and sc["type"] != "end":
            if st["stage"] not in stage_cache:
                stage_cache[st["stage"]] = stage_layer(spec["stages"], st["stage"])
            frame.alpha_composite(stage_cache[st["stage"]])

        c = st["chunk"]
        if sc["type"] != "end" and t < c["last_end"] + 0.6:
            shown = sum(1 for wt in c["word_t"] if wt <= t + 0.05)
            ck = (id(c), shown)
            if ck not in cap_cache:
                cap_cache[ck] = caption_layer(c["words"], shown)
            frame.alpha_composite(cap_cache[ck])
        rgb = frame.convert("RGB")
        if writer:
            writer.stdin.write(rgb.tobytes())
        if i in preview_at:
            rgb.save(os.path.join(out_dir, f"preview_{i // FPS:03d}s.jpg"), quality=85)
    if writer:
        writer.stdin.close()
        writer.wait()

    write_srt(chunks, os.path.join(out_dir, "captions.srt"))
    write_cover(spec, bg, os.path.join(out_dir, "cover.jpg"))
    print(f"rendered {n_frames} frames ({total:.1f}s) -> {video_path}")


def write_cover(spec, bg, path):
    c = spec["cover"]
    img = Image.fromarray(bg[:H]).convert("RGBA")
    d = ImageDraw.Draw(img)
    cx = W // 2
    f = label_font(44)
    tw = d.textlength(c["kicker"], font=f)
    pill(d, int(cx - tw / 2 - 30), 420, c["kicker"], f, ORANGE + (255,), (255, 255, 255))
    if c.get("emoji"):
        e = emoji(c["emoji"], 220)
        img.alpha_composite(e, (cx - e.width // 2, 560))
    centered(d, cx, 920, c["line1"], fit(c["line1"], "Black", 170), DEEP)
    centered(d, cx, 1090, c["line2"], fit(c["line2"], "Black", 110), ORANGE)
    tf = font("Black", 52)
    tw = d.textlength(c["tag"], font=tf)
    d.rounded_rectangle([cx - tw / 2 - 36, 1200, cx + tw / 2 + 36, 1300], 50, fill=TEAL)
    centered(d, cx, 1250, c["tag"], tf, (255, 255, 255))
    centered(d, cx, 1420, "mindsel.my", label_font(46), TEAL)
    img.convert("RGB").save(path, quality=92)


if __name__ == "__main__":
    main()
