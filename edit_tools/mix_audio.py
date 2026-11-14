#!/usr/bin/env python3
"""Final sound mix: levelled dialogue + VO + SFX on visible actions + music beds ducked under speech.

Run with the video-use venv (numpy):  ~/Developer/video-use/.venv/bin/python edit_tools/mix_audio.py
Writes edit/mix.wav (pre-master) and edit/mix_master.wav (two-pass loudnorm -14 LUFS, -1 dBTP).
"""
import json
import re
import subprocess
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
EDIT = REPO / "footage" / "KIAR PSA" / "edit"
SR = 48000
TLR = json.loads((EDIT / "timeline.json").read_text())
TL = {r["id"]: r for r in TLR}
TOTAL = max(r["out_end"] for r in TLR)
N = int(round(TOTAL * SR))


def T(rid, off=0.0):
    return TL[rid]["out_start"] + off


def END(rid, off=0.0):
    return TL[rid]["out_end"] + off


def load(path, af=None):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path)]
    if af:
        cmd += ["-af", af]
    cmd += ["-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
    return np.frombuffer(subprocess.check_output(cmd), dtype=np.float32).reshape(-1, 2).copy()


def db(x):
    return 10 ** (x / 20)


def place(bus, clip, t, gain=1.0, src_off=0.0):
    a = clip[int(src_off * SR):]
    s = int(round(t * SR))
    if s < 0:
        a, s = a[-s:], 0
    e = min(N, s + len(a))
    if e > s:
        bus[s:e] += a[: e - s] * gain


def attack(clip, thresh_db=-30):
    """Seconds from file start to the transient (first sample within 30 dB of peak)."""
    env = np.abs(clip).max(axis=1)
    pk = env.max() + 1e-9
    idx = np.argmax(env > pk * db(thresh_db))
    return idx / SR


def fade(clip, fin, fout):
    n = len(clip)
    g = np.ones(n, dtype=np.float32)
    a, b = int(fin * SR), int(fout * SR)
    if a:
        g[:a] = np.linspace(0, 1, a)
    if b:
        g[n - b:] = np.minimum(g[n - b:], np.linspace(1, 0, b))
    return clip * g[:, None]


# ---------------------------------------------------------------- dialogue (levelled per range)
dlg = load(EDIT / "dialogue.wav")[:N]
dlg = np.pad(dlg, ((0, N - len(dlg)), (0, 0)))
TARGET = db(-21)  # RMS of active speech
for r in TLR:
    if r["mute"] or r["source"] == "@black":
        continue
    s, e = int(r["out_start"] * SR), int(r["out_end"] * SR)
    seg = dlg[s:e]
    env = np.abs(seg).max(axis=1)
    act = seg[env > db(-42)]
    if len(act) < SR * 0.2:
        continue
    rms = np.sqrt((act ** 2).mean())
    g = float(np.clip(TARGET / (rms + 1e-9), db(-6), db(9)))
    dlg[s:e] = seg * g

# ---------------------------------------------------------------- voice-over
vo = np.zeros((N, 2), np.float32)
speech_spans = []
plan_p = EDIT / "vo" / "vo_plan.json"
for v in json.loads(plan_p.read_text()) if plan_p.exists() else []:
    af = None
    if v.get("fx") == "phone":
        af = "highpass=f=320,lowpass=f=3300,acompressor=threshold=-20dB:ratio=4,volume=1.2"
    elif v.get("fx") == "broadcast":
        af = "highpass=f=90,acompressor=threshold=-18dB:ratio=3"
    clip = load(EDIT / v["file"], af)
    rms = np.sqrt((clip[np.abs(clip).max(axis=1) > db(-42)] ** 2).mean())
    place(vo, clip, v["start"], TARGET / (rms + 1e-9) * db(v.get("gain_db", 0)))
    speech_spans.append((v["start"], v["start"] + v["duration"]))

# speech activity from captions (dialogue) for ducking
for c in json.loads((EDIT / "captions.json").read_text()):
    speech_spans.append((c["start"], c["end"]))

# ---------------------------------------------------------------- SFX (each tied to a visible action)
SFX = EDIT / "sfx"
# (file, time of the visible hit, gain dB, align transient?)
events = [
    ("riser", END("cold", -0.05), -12, "end"),          # swells into the glitch cut
    ("glitch", END("cold", -0.22), -9, True),
    ("glitch", T("lab_walk", 2.83), -10, True),          # HAZARDOUS -> SAFE flip
    ("title_boom", T("title", 0.35), -6, True),          # title words land
    ("envelope", T("s4_bribe", 1.2), -8, False),         # 'a small bonus' - envelope slides
    ("keyboard", T("s4_type", 0.2), -16, False),
    ("glitch", T("s4_safe", 1.6), -12, True),
    ("usb", T("s4_usb", 0.6), -10, True),
    ("stamp", T("s5_stamp", 0.51), -5, True),             # COMPLIANT slam
    ("whoosh", T("s6_news", 0.0), -9, True),
    ("news", T("s6_news", 1.2), -10, True),
    ("drop", T("s6_drop", 0.5), -8, True),
    ("monitor", T("s7_enter", 0.6), -24, False),
    ("dial", T("s7_dial", 0.25), -14, False),
    ("footsteps", T("s7_raid", 0.3), -14, False),
    ("cuffs", T("s7_arrest1", 2.4), -10, True),
    ("cuffs", T("s7_tan_b", 1.1), -10, True),
    ("final_hit", T("s8_close", 8.9), -8, True),         # MACC 997 reveal
]
fx = np.zeros((N, 2), np.float32)
for name, t, gdb, align in events:
    clip = load(SFX / f"{name}.mp3")
    clip = clip / (np.abs(clip).max() + 1e-9)  # peak-normalise, then set level
    if align == "end":
        start = t - len(clip) / SR
    elif align:
        start = t - attack(clip)
    else:
        start = t
    place(fx, fade(clip, 0.005, 0.08), start, db(gdb))

# ---------------------------------------------------------------- music beds
MUS = EDIT / "music"
beds = [  # file, out start, out end, src offset, fade in, fade out, level dB
    ("Suspense_and_Tension-stem-7-1min.mp3", T("lab_wide"), T("s4_lab", 1.0), 0.0, 1.5, 2.0, -17),
    ("Suspense_and_Tension-stem-3-1min.mp3", T("s4_lab", -0.5), T("s6_news", 0.1), 0.0, 1.5, 0.6, -18),
    ("The_darkest_hour.mp3", T("s6_news", 1.2), T("s8_notice", 0.6), 0.0, 0.8, 1.2, -16),
    ("Emotional_-_Piano_Instrumental.mp3", T("s8_notice", 0.2), TOTAL, 0.0, 1.2, 3.0, -15),
]
mus = np.zeros((N, 2), np.float32)
for f, s, e, off, fi, fo, ldb in beds:
    clip = load(MUS / f)
    rms = np.sqrt((clip ** 2).mean())
    clip = clip[int(off * SR): int(off * SR) + int((e - s) * SR)]
    place(mus, fade(clip, fi, fo) * (db(ldb) / (rms + 1e-9)), s)

# duck music under every spoken line: -13 dB, 0.25 s ramps
duck = np.ones(N, np.float32)
for s, e in speech_spans:
    a, b = max(0, int((s - 0.15) * SR)), min(N, int((e + 0.2) * SR))
    duck[a:b] = db(-13)
k = int(0.25 * SR)
duck = np.convolve(duck, np.ones(k) / k, mode="same").astype(np.float32)
mus *= duck[:, None]

mix = dlg + vo + fx + mus
pk = np.abs(mix).max()
if pk > 0.98:
    mix *= 0.98 / pk
raw = (EDIT / "mix.wav")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                "-c:a", "pcm_s24le", str(raw)], input=mix.astype(np.float32).tobytes(), check=True)

# two-pass loudnorm
m = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af",
                    "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                   capture_output=True, text=True).stderr
j = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", m, re.S).group(0))
af = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:"
      f"measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", af, "-ar", "48000", "-c:a", "pcm_s24le",
                str(EDIT / "mix_master.wav")], check=True)
print("mix:", EDIT / "mix_master.wav", f"{TOTAL:.2f}s;", len(events), "sfx;", len(speech_spans), "speech spans")
