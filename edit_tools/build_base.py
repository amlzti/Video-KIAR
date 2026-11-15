#!/usr/bin/env python3
"""Build the graded, cut base video + output-timeline captions from edl.json.

Per-segment extract (grade + 30 ms audio fades baked in) -> lossless concat.
Muted ranges get silent audio (their sound is replaced by VO / SFX / music later).

Usage: python edit_tools/build_base.py [--preview]
Outputs (in <footage>/edit/): base.mp4, timeline.json, captions.json
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EDL = json.loads((REPO / "edit_tools" / "edl.json").read_text())
FOOT = REPO / EDL["footage_dir"]
EDIT = FOOT / "edit"
FPS = EDL["fps"]

# "Toxic haze" grade: slightly desaturated, warm-sick highlights, cool shadows, soft vignette.
GRADE = (
    "eq=contrast=1.07:brightness=-0.015:saturation=0.84:gamma=0.98,"
    "colorbalance=rs=-0.035:gs=0.01:bs=0.035:rm=-0.015:gm=0.01:bm=0.0:rh=0.015:gh=0.0:bh=-0.015,"
    "curves=master='0/0.025 0.25/0.225 0.75/0.775 1/0.975',"
    "vignette=PI/5"
)

# HLG/PQ iPhone sources -> Rec.709 SDR (mobius keeps skin brighter than hable at 203-nit ref white).
TONEMAP = ("zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=mobius:param=0.3:desat=0,"
           "zscale=t=bt709:m=bt709:r=tv,format=yuv420p,")
COLOR_TAGS = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]


def is_portrait(video: Path) -> bool:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height:stream_side_data=rotation", "-of", "json", str(video)])
    st = json.loads(out)["streams"][0]
    rot = next((abs(int(sd.get("rotation", 0))) for sd in st.get("side_data_list", []) if "rotation" in sd), 0)
    w, h = (st["height"], st["width"]) if rot in (90, 270) else (st["width"], st["height"])
    return h > w


def is_hdr(video: Path) -> bool:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=color_transfer", "-of", "csv=p=0", str(video)]).decode()
    return out.strip().strip(",") in ("arib-std-b67", "smpte2084")


# Per-range caption fixes for ASR mishearings (token sequence -> replacement text).
FIXES = {
    "s2_cough": [("feel", "feels")],
    "s3_report": [("census", "sensor")],
    "s3_argue": [("And Chad,", "Encik,")],
    "s4_bribe": [("I'm sure", "Encik,")],
    "s5_reportx": [("admission", "emission")],
    "s5_within": [("ready, malignant", "within the limit.")],
    "s7_macc": [("MNCC.", "MACC?")],
    "s7_tan_a": [("Captain,", "Encik Tan,")],
}


def src_path(name: str) -> Path:
    base = FOOT
    if name.startswith("@stock/"):
        base, name = FOOT / "stock", name[len("@stock/"):]
    for ext in (".MOV", ".mp4", ".mov", ".MP4", ".webm"):
        p = base / f"{name}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(name)


def run(cmd):
    subprocess.run(cmd, check=True)


def extract(r, out: Path, w: int, h: int):
    n = round((r["end"] - r["start"]) * FPS)
    dur = n / FPS
    vf = f"tpad=stop_mode=clone:stop_duration=0.5,fps={FPS},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    venc = ["-frames:v", str(n), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-g", str(FPS),
            "-pix_fmt", "yuv420p", *COLOR_TAGS]
    aenc = ["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"]
    pad = f"apad,atrim=0:{dur:.6f}"
    if r["source"] == "@black":
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={FPS}:d={dur}",
             "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dur}", "-af", pad, *venc, *aenc, str(out)])
        return
    src = src_path(r["source"])
    if is_portrait(src):  # crop-to-fill instead of pillarboxing; crop_y picks the band (0 top .. 1 bottom)
        cy = r.get("crop_y", 0.5)
        vf = vf.replace(f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
                        f"scale={w}:-2,crop={w}:{h}:0:(ih-{h})*{cy}")
    if is_hdr(src):
        vf = vf.replace("tpad=", TONEMAP + "tpad=", 1)
    if r.get("mute"):
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{r['start']}", "-i", str(src), "-f", "lavfi",
             "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dur + 0.5}", "-map", "0:v:0", "-map", "1:a:0",
             "-vf", f"{vf},{GRADE},format=yuv420p", "-af", pad, *venc, *aenc, str(out)])
    else:
        af = f"aresample=48000,{pad},afade=t=in:st=0:d=0.03,afade=t=out:st={dur - 0.03:.3f}:d=0.03"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{r['start']}", "-i", str(src), "-t", f"{dur + 0.5}",
             "-map", "0:v:0", "-map", "0:a:0", "-vf", f"{vf},{GRADE},format=yuv420p", "-af", af,
             *venc, *aenc, str(out)])


def words_for(r):
    tj = EDIT / "transcripts" / f"{r['source']}.json"
    d = json.loads(tj.read_text())
    ws = [w for w in d["words"] if w.get("type") == "word"
          and w["start"] >= r["start"] - 0.02 and w["end"] <= r["end"] + 0.05]
    return [{"text": w["text"], "start": w["start"], "end": w["end"]} for w in ws]


def apply_fixes(rid, ws):
    for old, new in FIXES.get(rid, []):
        n = len(old.split())
        for i in range(len(ws) - n + 1):
            if " ".join(w["text"] for w in ws[i:i + n]) == old:
                ws[i:i + n] = [{"text": new, "start": ws[i]["start"], "end": ws[i + n - 1]["end"]}]
                break
    return ws


def chunk(ws, max_words=7):
    groups, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        gap = (nxt["start"] - w["end"]) if nxt else 9
        sent_end = re.search(r"[.?!]$", w["text"]) is not None
        comma = w["text"].endswith(",")
        if (nxt is None or gap >= 0.45 or len(cur) >= max_words
                or (sent_end and len(cur) >= 2) or (comma and len(cur) >= 4)):
            groups.append(cur)
            cur = []
    out = []
    for g in groups:  # fold 1-word orphans into a close neighbour
        if out and len(g) == 1 and g[0]["start"] - out[-1][-1]["end"] < 0.5 and len(out[-1]) < 8:
            out[-1].extend(g)
        else:
            out.append(g)
    return out


def tidy(caps):
    caps.sort(key=lambda c: c["start"])
    merged = []
    for c in caps:  # join a dangling 1-word group to the next one across a cut ("Here's" | "some gift")
        if merged and len(merged[-1]["text"].split()) == 1 and c["start"] - merged[-1]["end"] < 0.5:
            merged[-1] = {**merged[-1], "end": c["end"], "range": c["range"],
                          "text": merged[-1]["text"].rstrip(",") + " " + c["text"]}
        else:
            merged.append(dict(c))
    for a, b in zip(merged, merged[1:]):  # never overlap: one group on screen at a time
        if a["end"] > b["start"] - 0.03:
            a["end"] = round(b["start"] - 0.03, 3)
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="720p base")
    ap.add_argument("--only", default="", help="comma list of range ids to re-extract (others reuse segments)")
    a = ap.parse_args()
    w, h = (1280, 720) if a.preview else (EDL["width"], EDL["height"])
    segdir = EDIT / ("segs_720" if a.preview else "segs_1080")
    segdir.mkdir(parents=True, exist_ok=True)

    timeline, captions, t = [], [], 0.0
    seg_files = []
    for i, r in enumerate(EDL["ranges"]):
        out = segdir / f"{i:02d}_{r['id']}.mkv"
        if not a.only or r["id"] in a.only.split(",") or not out.exists():
            extract(r, out, w, h)
        seg_files.append(out)
        real = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                              "-of", "csv=p=0", str(out)]).decode().strip())
        dur = round(round((r["end"] - r["start"]) * FPS) / FPS, 6)
        entry = {"id": r["id"], "source": r["source"], "beat": r["beat"], "mute": bool(r.get("mute")),
                 "src_start": r["start"], "src_end": r["end"], "out_start": round(t, 3),
                 "out_end": round(t + dur, 3), "cam": r.get("cam"), "trans_out": r.get("trans_out")}
        tr = r.get("trans_out")
        if tr and tr["type"] == "dissolve":  # graded source frames just past the cut, for a real cross-dissolve
            taildir = EDIT / ("tails_720" if a.preview else "tails")
            taildir.mkdir(exist_ok=True)
            tail = taildir / f"{r['id']}.mkv"
            if not a.only or r["id"] in a.only.split(",") or not tail.exists():
                extract({**r, "start": r["end"], "end": r["end"] + tr["dur"], "mute": True}, tail, w, h)
            tmp4 = taildir / f"{r['id']}.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-i", str(tail), "-an", "-c:v", "copy", str(tmp4)])
            entry["tail"] = f"{taildir.name}/{r['id']}.mp4"
        timeline.append(entry)
        if not r.get("mute") and r["source"] != "@black":
            for g in chunk(apply_fixes(r["id"], words_for(r))):
                s = max(t, g[0]["start"] - r["start"] + t - 0.05)
                e = min(t + dur, g[-1]["end"] - r["start"] + t + 0.12)
                captions.append({"range": r["id"], "start": round(s, 3), "end": round(e, 3),
                                 "text": " ".join(x["text"] for x in g)})
        t += dur
        print(f"  {r['id']:<11} {dur:6.2f}s  (file {real:.2f}s)  -> {t:7.2f}s")

    lst = segdir / "concat.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in seg_files))
    base = EDIT / ("base_720.mp4" if a.preview else "base.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", f"setpts=N/{FPS}/TB", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-g", str(FPS), "-pix_fmt", "yuv420p", *COLOR_TAGS,
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(base)])
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vn", "-c:a",
         "pcm_s16le", str(EDIT / ("dialogue_720.wav" if a.preview else "dialogue.wav"))])
    captions = tidy(captions)
    (EDIT / "timeline.json").write_text(json.dumps(timeline, indent=1))
    (EDIT / "captions.json").write_text(json.dumps(captions, indent=1))
    print(f"base: {base}  total {t:.2f}s, {len(captions)} caption groups")


if __name__ == "__main__":
    main()
