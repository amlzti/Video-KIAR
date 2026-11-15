#!/usr/bin/env python3
"""Generate the HyperFrames project (graphics + captions over the graded base cut).

Design: "Sensor Forensics" - smog-dark glass, toxic amber, alarm red, fake-safe green,
JetBrains Mono data readouts, Oswald condensed display, Inter captions.
Every time below is derived from edit/timeline.json, so re-cutting never desyncs graphics.

Usage: python edit_tools/build_hf.py [--preview]
"""
import argparse
import html
import json
import os
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EDIT = REPO / "footage" / "KIAR PSA" / "edit"
HF = EDIT / "hf"
TL = {r["id"]: r for r in json.loads((EDIT / "timeline.json").read_text())}
TOTAL = max(r["out_end"] for r in TL.values())
VO = json.loads((EDIT / "vo" / "vo_plan.json").read_text()) if (EDIT / "vo" / "vo_plan.json").exists() else []


def T(rid, off=0.0):
    return round(TL[rid]["out_start"] + off, 3)


def END(rid, off=0.0):
    return round(TL[rid]["out_end"] + off, 3)


def esc(s):
    return html.escape(s, quote=True)


CSS_TOKENS = """
  --ink:#0B0F0E; --glass:rgba(10,13,12,.78); --amber:#FFB000; --red:#FF3B30; --green:#3DFF8E;
  --paper:#EEF0E8; --dim:#9AA39D;
"""

BASE_STYLE = """
  #root { position:absolute; inset:0; }
  .mono { font-family:'JetBrains Mono', monospace; letter-spacing:.08em; text-transform:uppercase; }
  .disp { font-family:'Oswald', sans-serif; font-weight:700; text-transform:uppercase; letter-spacing:.01em; }
  .card { position:absolute; background:var(--glass); border-left:6px solid var(--amber);
          padding:14px 26px 16px 22px; color:var(--paper); box-shadow:0 10px 40px rgba(0,0,0,.35); }
  .card .k { font-family:'JetBrains Mono', monospace; font-size:28px; letter-spacing:.14em; color:var(--amber);
             text-transform:uppercase; }
  .card .n { font-family:'Oswald', sans-serif; font-weight:700; font-size:46px; line-height:1.05; text-transform:uppercase; }
"""


class Comp:
    """One sub-composition spanning the whole film; children carry absolute times."""

    def __init__(self, cid, css=""):
        self.cid, self.css, self.items, self.js = cid, css, [], []

    def el(self, eid, start, dur, inner, style="", cls=""):
        self.items.append(
            f'<div id="{self.cid}-{eid}" class="clip {cls}" data-start="{start:.3f}" data-duration="{dur:.3f}" '
            f'style="{style}">{inner}</div>')
        return f"#{self.cid}-{eid}"

    def tw(self, line):
        self.js.append(line)

    def write(self):
        body = "\n    ".join(self.items)
        js = "\n    ".join(self.js)
        doc = f"""<template>
  <style>
    :root {{{CSS_TOKENS}}}
    {BASE_STYLE}
    {self.css}
  </style>
  <div id="root" data-composition-id="{self.cid}" data-width="1920" data-height="1080" data-layout-allow-overlap>
    {body}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    {js}
    window.__timelines["{self.cid}"] = tl;
  </script>
</template>
"""
        (HF / "compositions" / f"{self.cid}.html").write_text(doc)


def card_in(c, sel, t, d, x_from=-30):
    c.tw(f'tl.fromTo("{sel}", {{opacity:0, x:{x_from}, filter:"blur(8px)"}}, '
         f'{{opacity:1, x:0, filter:"blur(0px)", duration:0.45, ease:"expo.out"}}, {t:.3f});')
    c.tw(f'tl.to("{sel}", {{opacity:0, filter:"blur(6px)", duration:0.25, ease:"power2.in"}}, {t + d - 0.27:.3f});')


def name_card(c, eid, start, dur, kicker, name, x, y, right=False):
    pos = f"right:{x}px;" if right else f"left:{x}px;"
    sel = c.el(eid, start, dur, f'<div class="k">{esc(kicker)}</div><div class="n">{esc(name)}</div>',
               style=f"{pos}top:{y}px;", cls="card")
    card_in(c, sel, start, dur, x_from=30 if right else -30)


def aqi_meter(c, eid, start, dur, label, value, unit, status, frac, color, x=90, y=130):
    inner = (f'<div class="k">{esc(label)}</div>'
             f'<div style="display:flex;align-items:baseline;gap:14px">'
             f'<span class="disp aqi-v" style="font-size:84px;line-height:1;color:{color}">{esc(value)}</span>'
             f'<span class="mono" style="font-size:28px;color:var(--dim)">{esc(unit)}</span></div>'
             f'<div class="mono" style="font-size:28px;color:{color};margin-top:4px">● {esc(status)}</div>'
             f'<div style="margin-top:12px;height:8px;width:330px;background:rgba(255,255,255,.12)">'
             f'<div class="bar" style="height:8px;width:330px;transform-origin:left;background:{color}"></div></div>')
    sel = c.el(eid, start, dur, inner, style=f"right:{x}px;top:{y}px;border-left-color:{color};", cls="card")
    card_in(c, sel, start, dur, x_from=30)
    c.tw(f'tl.fromTo("{sel} .bar", {{scaleX:0}}, {{scaleX:{frac}, duration:1.1, ease:"power3.out"}}, {start + 0.25:.3f});')


def glitch_burst(c, eid, t, dur=0.36):
    """Deterministic RGB-split bar glitch, full frame, for cuts tied to falsified data."""
    bars = []
    rnd = [0.13, 0.71, 0.42, 0.88, 0.27, 0.56, 0.05, 0.93, 0.36, 0.64]
    for i, r in enumerate(rnd):
        top = int(r * 1000)
        h = 18 + int(((i * 37) % 9) * 9)
        col = ["var(--red)", "var(--green)", "#fff", "var(--amber)"][i % 4]
        bars.append(f'<div class="gb" style="position:absolute;left:0;top:{top}px;width:1920px;height:{h}px;'
                    f'background:{col};mix-blend-mode:difference;opacity:.85"></div>')
    sel = c.el(eid, t, dur, "".join(bars), style="position:absolute;inset:0;")
    for i in range(len(rnd)):
        dx = [-140, 220, -60, 310, -260, 90, 180, -200, 40, -120][i]
        c.tw(f'tl.fromTo("{sel} .gb:nth-child({i + 1})", {{x:{dx}, scaleY:1}}, '
             f'{{x:{-dx // 2}, scaleY:{0.3 + (i % 3) * 0.4}, duration:{dur:.2f}, ease:"steps(4)"}}, {t:.3f});')


# ------------------------------------------------------------------ scenes

LB = 104  # letterbox bar height (2.2:1 short-film frame)


def cam_xform(s, fx, fy, k=0.35):
    """Translate that zooms by s toward focus (fx, fy), clamped so frame edges never show."""
    cx, cy = 960, 540
    fxp, fyp = fx * 1920, fy * 1080
    tx = (k - s) * (fxp - cx)
    ty = (k - s) * (fyp - cy)
    mx, my = (s - 1) * cx, (s - 1) * cy
    return round(max(-mx, min(mx, tx)), 1), round(max(-my, min(my, ty)), 1)


def camera():
    c = Comp("camera", css="""
      #camera-w, .tailw { position:absolute; inset:0; transform-origin:50% 50%; }
      #camera-w video, .tailw video { position:absolute; left:0; top:0; width:1920px; height:1080px; object-fit:cover; }
      .lb { position:absolute; left:0; width:1920px; background:#000; }
    """)
    vids = [f'<div id="camera-w"><video id="camera-base" class="clip" src="assets/base.mp4" data-start="0" '
            f'data-duration="{TOTAL:.3f}" muted playsinline></video></div>']
    rows = sorted(TL.values(), key=lambda r: r["out_start"])
    last_state = {}
    for r in rows:
        t0, t1 = r["out_start"], r["out_end"]
        kfs = r.get("cam") or [[0, 1.0, .5, .5, "cut"]]
        prev_t = None
        for (dt, sc, fx, fy, mode) in kfs:
            x, y = cam_xform(sc, fx, fy)
            at = round(min(t0 + dt, t1 - 0.034), 3)  # land before the next shot's cut
            if mode == "cut" or prev_t is None:
                c.tw(f'tl.set("#camera-w", {{scale:{sc}, x:{x}, y:{y}}}, {at});')
            else:
                c.tw(f'tl.to("#camera-w", {{scale:{sc}, x:{x}, y:{y}, duration:{at - prev_t:.3f}, ease:"sine.inOut"}}, {prev_t:.3f});')
            prev_t = at
            last_state[r["id"]] = (sc, x, y)
    # transitions into the next shot
    for r in rows:
        tr = r.get("trans_out")
        if not tr:
            continue
        d, t1 = tr["dur"], r["out_end"]
        if tr["type"] == "dissolve" and r.get("tail"):
            sc, x, y = last_state[r["id"]]
            shutil.copy(EDIT / r["tail"], HF / "assets" / f"tail_{r['id']}.mp4")
            vids.append(f'<div class="tailw" id="camera-tw-{r["id"]}" style="opacity:0">'
                        f'<video id="camera-tail-{r["id"]}" class="clip" src="assets/tail_{r["id"]}.mp4" '
                        f'data-start="{t1:.3f}" data-duration="{d:.3f}" muted playsinline></video></div>')
            c.tw(f'tl.set("#camera-tw-{r["id"]}", {{scale:{sc}, x:{x}, y:{y}}}, 0);')
            c.tw(f'tl.fromTo("#camera-tw-{r["id"]}", {{opacity:1}}, {{opacity:0, duration:{d:.3f}, ease:"sine.inOut"}}, {t1:.3f});')
            c.tw(f'tl.set("#camera-tw-{r["id"]}", {{opacity:0}}, {t1 + d:.3f});')
        elif tr["type"] == "dip":
            sel = c.el(f"dip-{r['id']}", t1 - d / 2, d, "", style="position:absolute;inset:0;background:#000;opacity:0;")
            c.tw(f'tl.fromTo("{sel}", {{opacity:0}}, {{opacity:1, duration:{d / 2:.3f}, ease:"power1.in"}}, {t1 - d / 2:.3f});')
            c.tw(f'tl.to("{sel}", {{opacity:0, duration:{d / 2:.3f}, ease:"power1.out"}}, {t1:.3f});')
    c.items = vids + c.items
    c.items.append(f'<div class="lb" style="top:0;height:{LB}px"></div><div class="lb" style="bottom:0;height:{LB}px"></div>')
    c.write()
    return c


def hook():
    c = Comp("hook")
    # flash-forward tag on the cold open (right side is empty glass wall)
    sel = c.el("ff", T("cold", 0.1), 1.6, '<span class="mono" style="font-size:28px;color:var(--amber)">'
               '● 21 DAYS LATER</span>', style="position:absolute;right:80px;top:130px;")
    c.tw(f'tl.fromTo("{sel}", {{opacity:0}}, {{opacity:1, duration:0.2}}, {T("cold", 0.1)});')
    glitch_burst(c, "g1", END("cold", -0.22), 0.34)

    # sensor HUD over the empty lab + laptop push-in (no faces in these shots)
    t0, t1 = T("lab_wide", 0.35), END("lab_walk", -0.05)
    rows = [("SENSOR 07 · STACK B · LIVE", "var(--dim)"), ("PM2.5 ........ 212 µg/m³", "var(--paper)"),
            ("SO₂ .......... 0.41 ppm", "var(--paper)"), ("NO₂ .......... 0.19 ppm", "var(--paper)")]
    inner = "".join(f'<div class="row mono" style="font-size:30px;color:{col};margin:6px 0">{esc(t)}</div>'
                    for t, col in rows)
    inner += ('<div class="mono" style="font-size:30px;margin-top:18px;color:var(--paper)">STATUS&nbsp;&nbsp;'
              '<span style="display:inline-grid"><span class="st-bad" style="grid-area:1/1;color:var(--red)">HAZARDOUS</span>'
              '<span class="st-ok" style="grid-area:1/1;color:var(--green);opacity:0">SAFE</span></span></div>')
    sel = c.el("hud", t0, t1 - t0, inner, style="left:110px;top:300px;", cls="card")
    c.tw(f'tl.fromTo("{sel}", {{opacity:0}}, {{opacity:1, duration:0.3}}, {t0:.3f});')
    for i in range(len(rows)):
        c.tw(f'tl.fromTo("{sel} .row:nth-child({i + 1})", {{opacity:0, x:-12}}, {{opacity:1, x:0, duration:0.25, '
             f'ease:"power3.out"}}, {t0 + 0.25 + i * 0.32:.3f});')
    flip = T("lab_walk", 2.95)  # laptop fills frame: the number gets changed
    c.tw(f'tl.to("{sel} .st-bad", {{opacity:0, duration:0.05, ease:"steps(1)"}}, {flip:.3f});')
    c.tw(f'tl.to("{sel} .st-ok", {{opacity:1, duration:0.05, ease:"steps(1)"}}, {flip + 0.05:.3f});')
    c.tw(f'tl.to("{sel}", {{borderLeftColor:"#3DFF8E", duration:0.05}}, {flip:.3f});')
    glitch_burst(c, "g2", flip - 0.12, 0.3)
    glitch_burst(c, "g3", END("lab_walk", -0.18), 0.3)
    c.write()
    return c


def title():
    c = Comp("title")
    t0, d = T("title"), TL["title"]["out_end"] - TL["title"]["out_start"]
    c.el("scrim", t0, d, "", style="position:absolute;inset:0;background:radial-gradient(ellipse at center,"
                                    "rgba(8,10,9,.55) 0%,rgba(8,10,9,.88) 75%);")
    inner = ('<div class="mono kick" style="font-size:30px;color:var(--amber);letter-spacing:.4em">'
             'A PUBLIC SERVICE ANNOUNCEMENT</div>'
             '<div class="disp" style="font-size:168px;line-height:.98;color:var(--paper);margin-top:18px">'
             '<span class="w">CLEAN</span> <span class="w">NUMBERS,</span></div>'
             '<div class="disp" style="font-size:168px;line-height:.98;color:var(--amber);'
             'text-shadow:0 0 40px rgba(255,176,0,.35)"><span class="w">DIRTY</span> <span class="w">AIR.</span></div>')
    sel = c.el("t", t0, d, inner, style="position:absolute;inset:0;display:flex;flex-direction:column;"
                                         "align-items:center;justify-content:center;text-align:center;")
    c.tw(f'tl.fromTo("{sel} .kick", {{opacity:0}}, {{opacity:1, duration:0.4}}, {t0 + 0.1:.3f});')
    c.tw(f'tl.fromTo("{sel} .w", {{opacity:0, filter:"blur(10px)"}}, {{opacity:1, filter:"blur(0px)", '
         f'duration:0.16, stagger:0.11, ease:"power4.out"}}, {t0 + 0.35:.3f});')
    c.tw(f'tl.to("{sel}", {{opacity:0, filter:"blur(8px)", duration:0.25, ease:"power2.in"}}, {t0 + d - 0.3:.3f});')
    c.write()
    return c


def tags():
    c = Comp("tags")
    # scene 2: school gate
    name_card(c, "loc2", T("s2_car", 0.4), 3.4, "07:42 AM · MONDAY", "SK Taman Harapan", 90, 820)
    aqi_meter(c, "aqi2", T("s2_car", 0.9), 3.0, "AIR QUALITY INDEX", "168", "AQI", "UNHEALTHY", 0.56, "var(--amber)")
    name_card(c, "mei", T("s2_cough", 1.3), 3.2, "His daughter", "Mei Ling", 90, 640, right=True)
    name_card(c, "tan", T("s2_promise", 0.9), 3.4, "Environmental Inspector", "Inspector Tan", 90, 700)
    # scene 3: factory
    name_card(c, "loc3", T("s3_fact", 0.2), 2.0, "Production floor · 09:15", "Harapan Plastics", 90, 820)
    aqi_meter(c, "aqi3", T("s3_report", 2.4), 3.6, "STACK EMISSION", "3.4×", "OF LEGAL LIMIT", "OVER LIMIT", 0.92,
              "var(--red)")
    name_card(c, "raz", T("s3_report", 0.3), 2.2, "Factory Manager", "Encik Razak", 90, 640, right=True)
    name_card(c, "emi", T("s3_argue", 0.4), 3.2, "Environmental Officer", "Emily", 90, 760, right=True)
    # scene 4: lab
    name_card(c, "ali", T("s4_lab", 0.3), 2.4, "Lab Analyst", "Alice", 120, 330)
    # scene 5: inspection day
    sel = c.el("loc5", T("s5_greet", 0.2), 2.6,
               '<div class="k">Harapan Plastics · 10:00 AM</div><div class="n">Inspection Day</div>',
               style="left:50%;top:124px;transform:translateX(-50%);border-left:none;border-top:6px solid var(--amber);"
                     "text-align:center;", cls="card")
    c.tw(f'tl.fromTo("{sel}", {{opacity:0, y:-20}}, {{opacity:1, y:0, duration:0.45, ease:"expo.out"}}, '
         f'{T("s5_greet", 0.2):.3f});')
    c.tw(f'tl.to("{sel}", {{opacity:0, duration:0.25}}, {T("s5_greet", 2.55):.3f});')
    # scene 7: hospital
    name_card(c, "loc7", T("s7_door", 0.1), 2.0, "Same day · 4:12 PM", "Harapan District Hospital", 90, 820)
    c.write()
    return c


def evidence():
    c = Comp("evidence", css="""
      .alert { position:absolute; background:rgba(255,59,48,.92); color:#fff; padding:10px 22px; }
      .stampw { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; }
      .stamp { display:inline-block; white-space:nowrap; border:12px solid var(--red); border-radius:10px;
               color:var(--red); font-family:'Oswald',sans-serif; font-weight:700; font-size:150px; line-height:1;
               letter-spacing:.06em; padding:22px 44px 26px 54px; background:rgba(255,59,48,.06);
               box-shadow:inset 0 0 0 5px rgba(255,59,48,.35); }
    """)
    # falsified reading on the laptop close-up
    t = T("s4_safe", 0.5)
    sel = c.el("edit", t, 3.1, '<div class="mono" style="font-size:30px;color:#fff">⚠ EDIT DETECTED · 23:14:07</div>'
               '<div class="mono" style="font-size:28px;color:#ffd9d6;margin-top:4px">'
               'AIR QUALITY: HAZARDOUS → SAFETY</div>', style="left:80px;top:130px;", cls="alert")
    card_in(c, sel, t, 3.1)
    glitch_burst(c, "g4", T("s4_safe", 1.6), 0.28)
    # Alice copies the raw log
    t = T("s4_usb", 0.6)
    inner = ('<div class="k">USB · KINGSTON 32GB</div>'
             '<div class="mono" style="font-size:28px;margin:6px 0 10px">COPYING RAW_SENSOR_LOG.csv</div>'
             '<div style="height:10px;width:460px;background:rgba(255,255,255,.12)">'
             '<div class="bar" style="height:10px;width:460px;transform-origin:left;background:var(--amber)"></div></div>'
             '<div class="mono done" style="font-size:28px;color:var(--green);margin-top:10px;opacity:0">'
             '✓ ORIGINAL DATA SECURED</div>')
    sel = c.el("usb", t, 5.8, inner, style="right:90px;top:130px;", cls="card")
    card_in(c, sel, t, 5.8, x_from=30)
    c.tw(f'tl.fromTo("{sel} .bar", {{scaleX:0}}, {{scaleX:1, duration:3.2, ease:"none"}}, {t + 0.4:.3f});')
    c.tw(f'tl.to("{sel} .done", {{opacity:1, duration:0.2}}, {t + 3.7:.3f});')
    # COMPLIANT stamp slam (no faces in this insert)
    t = T("s5_stamp", 0.35)
    sel = c.el("stamp", t, END("s5_stamp") - t, '<div class="stampw"><div class="stamp">COMPLIANT</div></div>',
               style="position:absolute;inset:0;")
    c.tw(f'tl.fromTo("{sel} .stamp", {{scale:2.4, rotation:-14, opacity:0}}, {{scale:1, rotation:-8, opacity:.92, '
         f'duration:0.16, ease:"power4.in"}}, {t:.3f});')
    c.tw(f'tl.fromTo("{sel} .stamp", {{x:0}}, {{x:6, duration:0.04, yoyo:true, repeat:5, ease:"none"}}, {t + 0.16:.3f});')
    # 20 students counter (window area, above the faces)
    t = T("s7_doctor", 3.0)
    inner = ('<div class="disp cnt" style="font-size:150px;line-height:1;color:var(--amber);text-shadow:0 4px 24px rgba(0,0,0,.6)">20</div>'
             '<div class="mono" style="font-size:30px;color:var(--paper);text-shadow:0 2px 12px rgba(0,0,0,.85)">STUDENTS · SAME SYMPTOMS</div>')
    sel = c.el("cnt", t, 2.95, inner, style="position:absolute;left:900px;top:130px;text-align:left;")
    c.tw(f'tl.fromTo("{sel}", {{opacity:0, filter:"blur(8px)"}}, {{opacity:1, filter:"blur(0px)", duration:0.3}}, {t:.3f});')
    c.tw(f'tl.to("{sel}", {{opacity:0, duration:0.25}}, {t + 2.65:.3f});')
    # 997 dial
    t = T("s7_dial", 0.2)
    inner = "".join(f'<span class="d disp" style="display:inline-block;font-size:220px;color:var(--paper)">{d}</span>'
                    for d in "997")
    inner = f'<div class="mono" style="font-size:30px;color:var(--amber)">DIALLING · MACC</div><div>{inner}</div>'
    sel = c.el("dial", t, END("s7_dial") - t, inner, style="position:absolute;left:1150px;width:640px;top:300px;text-align:right;")
    c.tw(f'tl.fromTo("{sel} .d", {{opacity:0, y:20}}, {{opacity:1, y:0, duration:0.18, stagger:0.42, '
         f'ease:"power3.out"}}, {t + 0.1:.3f});')
    # arrests
    for eid, rid, off, txt, side in [("ar1", "s7_arrest1", 1.9, "ARRESTED · GIVING AND TAKING BRIBES", "left:520px"),
                                     ("ar2", "s7_tan_b", 0.3, "ARRESTED · TAKING A BRIBE", "left:90px")]:
        t = T(rid, off)
        d = min(2.6, END(rid) - t) if rid == "s7_arrest1" else END(rid) - t
        sel = c.el(eid, t, d, f'<div class="mono" style="font-size:30px;letter-spacing:.14em">{txt}</div>',
                   style=f"{side};top:130px;", cls="alert")
        card_in(c, sel, t, d)
    # closure notice translation
    t = T("s8_notice", 0.8)
    inner = ('<div class="k">Notice of premises closure</div>'
             '<div style="font-family:Inter,sans-serif;font-size:30px;line-height:1.3;max-width:620px;margin-top:6px">'
             'Harapan Plastics is closed until further notice. All operations must stop until the air filtration '
             'system is upgraded and approved.</div>')
    sel = c.el("notice", t, 5.4, inner, style="left:90px;top:560px;border-left-color:var(--red);", cls="card")
    card_in(c, sel, t, 5.4)
    c.write()
    return c


def news():
    c = Comp("news", css="""
      .bug { position:absolute; left:80px; top:128px; display:flex; gap:12px; align-items:center; }
      .lt { position:absolute; left:80px; right:80px; bottom:190px; }
      .ticker { position:absolute; left:0; right:0; bottom:110px; height:56px; background:#111; overflow:hidden; }
    """)
    t0 = T("s6_smoke")
    d = END("s6_fact") - t0
    # "3 weeks later" chapter
    sel = c.el("later", t0, 2.9, '<div class="disp" style="font-size:120px;color:var(--paper);'
               'text-shadow:0 6px 40px rgba(0,0,0,.7)">3 WEEKS LATER</div>',
               style="position:absolute;inset:0;background:rgba(8,10,9,.45);display:flex;align-items:center;"
                     "justify-content:center;")
    c.tw(f'tl.fromTo("{sel} .disp", {{opacity:0, scale:1.08, filter:"blur(10px)"}}, '
         f'{{opacity:1, scale:1, filter:"blur(0px)", duration:0.3, ease:"expo.out"}}, {t0:.3f});')
    c.tw(f'tl.to("{sel}", {{opacity:0, filter:"blur(8px)", duration:0.3}}, {t0 + 2.55:.3f});')
    t1 = T("s6_amb1")
    dd = END("s6_fact") - t1
    c.el("bug", t1, dd, '<span style="background:var(--red);color:#fff;padding:6px 14px;font-size:28px" class="mono">● LIVE</span>'
                        '<span class="disp" style="font-size:40px;color:#fff">HARAPAN 24</span>',
         cls="bug")
    inner = ('<div style="display:flex;align-items:stretch">'
             '<div class="disp" style="background:var(--red);color:#fff;font-size:46px;padding:10px 22px">BREAKING</div>'
             '<div style="background:rgba(10,13,12,.9);color:#fff;padding:10px 26px;flex:1">'
             '<div class="disp hl" style="font-size:52px;line-height:1.1">Dozens of students treated for breathing problems</div>'
             '</div></div>'
             '<div class="mono" style="background:var(--amber);color:#111;display:inline-block;font-size:28px;'
             'padding:6px 18px">TAMAN HARAPAN INDUSTRIAL ESTATE</div>')
    sel = c.el("lt", t1, dd, inner, cls="lt")
    c.tw(f'tl.fromTo("{sel}", {{opacity:0, y:40}}, {{opacity:1, y:0, duration:0.45, ease:"expo.out"}}, {t1:.3f});')
    tick = ("AIR QUALITY INDEX 212 — HAZARDOUS  •  SCHOOLS ADVISED TO KEEP WINDOWS SHUT  •  "
            "RESIDENTS REPORT CHEMICAL SMELL NEAR STACK B  •  ") * 3
    sel = c.el("tk", t1, dd, f'<div class="mono tt" style="white-space:nowrap;font-size:28px;color:#fff;'
                             f'line-height:56px">{esc(tick)}</div>', cls="ticker")
    c.tw(f'tl.fromTo("{sel} .tt", {{x:0}}, {{x:-1400, duration:{dd:.2f}, ease:"none"}}, {t1:.3f});')
    c.write()
    return c


def closing():
    c = Comp("closing", css="""
      .line { font-family:'Inter',sans-serif; font-weight:600; color:var(--paper); font-size:46px; text-align:center; }
    """)
    t0 = T("s8_close")
    full = END("s8_close") - t0
    c.el("bg", t0, full, "", style="position:absolute;inset:0;background:#070908;")
    q = "One honest report could have protected every child in that school."
    words = "".join(f'<span class="w">{esc(w)} </span>' for w in q.split())
    sel = c.el("q", t0 + 0.4, 5.0, f'<div class="line" style="font-family:\'EB Garamond\',serif;font-style:italic;'
               f'font-weight:400;font-size:62px;max-width:1300px;line-height:1.25">{words}</div>',
               style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;")
    c.tw(f'tl.fromTo("{sel} .w", {{opacity:0}}, {{opacity:1, duration:0.12, stagger:0.27, ease:"none"}}, {t0 + 0.45:.3f});')
    c.tw(f'tl.to("{sel}", {{opacity:0, filter:"blur(6px)", duration:0.3}}, {t0 + 5.05:.3f});')
    facts = ["Giving a bribe and taking a bribe are both crimes.",
             "One honest report can protect a whole community."]
    inner = "".join(f'<div class="line f" style="margin:18px 0"><span style="color:var(--amber)">—</span> {esc(f)}</div>'
                    for f in facts)
    inner += ('<div class="cta" style="margin-top:46px;text-align:center">'
              '<div class="mono" style="font-size:30px;color:var(--dim);letter-spacing:.3em">REPORT CORRUPTION</div>'
              '<div class="disp" style="font-size:150px;line-height:1;color:var(--amber)">MACC 997</div></div>')
    sel = c.el("facts", t0 + 5.5, 6.6, inner, style="position:absolute;inset:0;display:flex;flex-direction:column;"
                                                    "align-items:center;justify-content:center;")
    c.tw(f'tl.fromTo("{sel} .f", {{opacity:0, y:14}}, {{opacity:1, y:0, duration:0.4, stagger:1.6, ease:"expo.out"}}, '
         f'{t0 + 5.6:.3f});')
    c.tw(f'tl.fromTo("{sel} .cta", {{opacity:0, scale:1.06, filter:"blur(10px)"}}, '
         f'{{opacity:1, scale:1, filter:"blur(0px)", duration:0.35, ease:"expo.out"}}, {t0 + 8.9:.3f});')
    c.tw(f'tl.to("{sel}", {{opacity:0, duration:0.35}}, {t0 + 11.75:.3f});')
    credits = ("Inspector Tan — Javier Lee · Mei Ling — Eavan Tan · Emily — Jessy Pang Xin Yuan · "
               "Alice — Chua Xin Ying · Doctor — Amalia Izzati · Encik Razak &amp; MACC officer — special appearances")
    music = ("Music: “Suspense and Tension” — 3minutetunes · “The darkest hour” — zero-project · "
             "“Emotional – Piano Instrumental” — E. Erkut (CC BY 3.0, Jamendo) · Voices &amp; SFX: ElevenLabs<br>"
             "B-roll via Wikimedia Commons: “Blue chimneys of the factory emit gases” — Fumikas Sagisavas (CC0) · "
             "“Ambulance running on road” — Free Video Library (CC BY 3.0) · "
             "“Department of Health Malaysia Ambulance” — BlueHelvetical (CC BY-SA 4.0)")
    inner = ('<div class="disp" style="font-size:96px;color:var(--paper);line-height:1">CLEAN NUMBERS, '
             '<span style="color:var(--amber)">DIRTY AIR.</span></div>'
             f'<div class="mono" style="font-size:28px;color:var(--dim);margin-top:36px;max-width:1760px;'
             f'line-height:1.7;text-transform:none;letter-spacing:.04em">{credits}<br>{music}</div>')
    sel = c.el("end", t0 + 12.2, full - 12.2, inner, style="position:absolute;inset:0;display:flex;"
               "flex-direction:column;align-items:center;justify-content:center;text-align:center;")
    c.tw(f'tl.fromTo("{sel}", {{opacity:0}}, {{opacity:1, duration:0.8, ease:"power2.out"}}, {t0 + 12.2:.3f});')
    c.write()
    return c


def captions():
    c = Comp("captions", css="""
      .cap { position:absolute; left:0; right:0; bottom:24px; text-align:center; }
      .cap span { display:inline-block; font-family:'Inter',sans-serif; font-weight:600; font-size:42px; color:#F4F5EF;
                  background:rgba(8,10,9,.58); padding:6px 18px 8px; border-radius:6px; }
      .cap.vo span { font-style:italic; color:#FFE3A3; }
    """)
    caps = json.loads((EDIT / "captions.json").read_text())
    for v in VO:
        for g in v.get("captions", []):
            caps.append({"start": g["start"], "end": g["end"], "text": g["text"], "vo": True})
    caps.sort(key=lambda x: x["start"])
    for a, b in zip(caps, caps[1:]):
        if a["end"] > b["start"] - 0.03:
            a["end"] = b["start"] - 0.03
    for i, g in enumerate(caps):
        d = round(g["end"] - g["start"], 3)
        if d < 0.25:
            continue
        sel = c.el(f"c{i}", g["start"], d, f"<span>{esc(g['text'])}</span>", cls="cap" + (" vo" if g.get("vo") else ""))
        c.tw(f'tl.fromTo("{sel} span", {{opacity:0}}, {{opacity:1, duration:0.1}}, {g["start"]:.3f});')
    c.write()
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()
    (HF / "compositions").mkdir(parents=True, exist_ok=True)
    (HF / "assets").mkdir(exist_ok=True)
    base = EDIT / ("base_720.mp4" if a.preview else "base.mp4")
    dst = HF / "assets" / "base.mp4"
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    os.link(base, dst)

    for f in (HF / "assets").glob("tail_*.mp4"):
        f.unlink()
    scenes = [camera(), hook(), title(), tags(), evidence(), news(), closing(), captions()]
    hosts = "\n      ".join(
        f'<div id="{s.cid}" data-composition-id="{s.cid}" data-composition-src="compositions/{s.cid}.html" '
        f'data-start="0" data-duration="{TOTAL:.3f}" data-track-index="{i + 1}" '
        f'data-track-kind="{"captions" if s.cid == "captions" else "graphics"}" data-width="1920" data-height="1080" '
        f'style="z-index:{i + 1}"></div>' for i, s in enumerate(scenes))
    index = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      * {{ margin:0; padding:0; box-sizing:border-box; }}
      html, body {{ width:1920px; height:1080px; overflow:hidden; background:#000; }}
      #root {{ position:relative; width:1920px; height:1080px; }}
      #base {{ position:absolute; left:0; top:0; width:1920px; height:1080px; object-fit:contain; z-index:1; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{TOTAL:.3f}" data-width="1920" data-height="1080">
      {hosts}
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""
    (HF / "index.html").write_text(index)
    print(f"wrote {HF} ({len(scenes)} scenes, {TOTAL:.2f}s)")


if __name__ == "__main__":
    main()
