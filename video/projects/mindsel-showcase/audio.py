#!/usr/bin/env python3
"""Synthesised soundtrack for the Mindsel app showcase: a calm looping pad, soft taps and pop swells.
Event times mirror the GSAP timeline in index.html. Writes out/audio.wav."""
import os
import wave

import numpy as np

SR, DUR = 44100, 15.0
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "audio.wav")
TAPS = [2.6, 4.3, 5.5, 9.0, 10.5, 11.35]
POPS = [0.45, 6.6, 11.55]
SLIDES = [2.85, 5.75, 9.25, 13.85]

n = int(SR * DUR)
t = np.arange(n) / SR
rng = np.random.default_rng(7)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def pad_note(freq, start, length, amp):
    """Soft detuned pad voice, stereo, with slow attack/release. Wraps around DUR so the loop is seamless."""
    out = np.zeros((n, 2))
    ln = int(length * SR)
    tt = np.arange(ln) / SR
    env = np.minimum(1, tt / 1.2) * np.minimum(1, (length - tt) / 1.4)
    env = np.clip(env, 0, 1) ** 1.5
    for det, pan in ((-0.0025, 0.2), (0.0, 0.5), (0.0025, 0.8)):
        f = freq * (1 + det)
        wave_ = sum(a * np.sin(2 * np.pi * f * k * tt + rng.uniform(0, 6)) for k, a in ((1, 1), (2, .28), (3, .08)))
        sig = wave_ * env * amp / 3
        idx = (int(start * SR) + np.arange(ln)) % n
        out[idx, 0] += sig * (1 - pan)
        out[idx, 1] += sig * pan
    return out


mix = np.zeros((n, 2))
# Cmaj9 -> Am9 -> Fmaj9 -> G6sus, 3.75s each, overlapping so the bar line never drops out
chords = [[48, 55, 64, 71, 74], [45, 52, 60, 67, 71], [41, 48, 57, 64, 67], [43, 50, 57, 62, 64]]
for i, ch in enumerate(chords):
    for m in ch:
        mix += pad_note(hz(m), i * 3.75 - 0.6, 5.0, 0.07 if m < 50 else 0.05)

# gentle plucked arpeggio, 8th notes at 64 bpm-ish
for i, ch in enumerate(chords):
    notes = [ch[2] + 12, ch[3] + 12, ch[4] + 12, ch[3] + 12]
    for j in range(4):
        st = i * 3.75 + j * 0.9375
        ln = 1.6
        tt = np.arange(int(ln * SR)) / SR
        f = hz(notes[j])
        s = (np.sin(2 * np.pi * f * tt) + .3 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt * 3.2) * 0.035
        s *= np.minimum(1, tt / 0.005)
        idx = (int(st * SR) + np.arange(len(tt))) % n
        pan = 0.35 + 0.3 * (j % 2)
        mix[idx, 0] += s * (1 - pan)
        mix[idx, 1] += s * pan


def add(sig, at, pan=0.5):
    i0 = int(at * SR)
    i1 = min(n, i0 + len(sig))
    mix[i0:i1, 0] += sig[: i1 - i0] * (1 - pan) * 2
    mix[i0:i1, 1] += sig[: i1 - i0] * pan * 2


# taps: short soft "tock"
for at in TAPS:
    tt = np.arange(int(0.12 * SR)) / SR
    tock = np.sin(2 * np.pi * 1400 * tt * np.exp(-tt * 18)) * np.exp(-tt * 55) * 0.16
    add(tock, at, 0.55)

# pops: airy upward swell + glassy chime
for at in POPS:
    tt = np.arange(int(0.9 * SR)) / SR
    noise = rng.standard_normal(len(tt))
    noise = np.convolve(noise, np.ones(6) / 6, mode="same") - np.convolve(noise, np.ones(60) / 60, mode="same")
    swell = noise * np.sin(np.pi * np.clip(tt / 0.7, 0, 1)) ** 2 * 0.05
    add(swell, at - 0.1)
    tt = np.arange(int(1.4 * SR)) / SR
    chime = sum(a * np.sin(2 * np.pi * f * tt) for f, a in ((1568, 1), (2349, .5), (3136, .25))) * np.exp(-tt * 4) * 0.03
    add(chime, at + 0.45, 0.6)

# slides: very soft whoosh
for at in SLIDES:
    tt = np.arange(int(0.6 * SR)) / SR
    noise = rng.standard_normal(len(tt))
    noise = np.convolve(noise, np.ones(30) / 30, mode="same")
    add(noise * np.sin(np.pi * tt / 0.6) ** 2 * 0.05, at, 0.4)

# simple stereo reverb (decaying noise IR), applied circularly so the tail wraps into the loop start
ir_len = int(2.2 * SR)
ir_t = np.arange(ir_len) / SR
out = np.zeros_like(mix)
size = 1 << int(np.ceil(np.log2(n)))
for c in range(2):
    ir = rng.standard_normal(ir_len) * np.exp(-ir_t * 2.6)
    ir = np.convolve(ir, np.ones(8) / 8, mode="same")
    ir /= np.sqrt((ir ** 2).sum())
    wet = np.fft.irfft(np.fft.rfft(mix[:, c], n) * np.fft.rfft(ir, n), n)  # circular convolution, length n
    out[:, c] = mix[:, c] + wet * 0.35
out /= np.abs(out).max() / 0.85

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with wave.open(OUT, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((out * 32767).astype("<i2").tobytes())
print("wrote", OUT)
