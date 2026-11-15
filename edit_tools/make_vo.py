#!/usr/bin/env python3
"""Generate the missing voice-over lines with ElevenLabs TTS (with word timings for captions).

The API key is injected by the session's network proxy (xi-api-key); nothing secret lives here.
Writes edit/vo/<id>.mp3 and edit/vo/vo_plan.json (placement + caption groups on the output timeline).
Usage: python edit_tools/make_vo.py
"""
import base64
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EDIT = REPO / "footage" / "KIAR PSA" / "edit"
VO = EDIT / "vo"
TL = {r["id"]: r for r in json.loads((EDIT / "timeline.json").read_text())}

# premade voices: Sarah (young, reassuring - Alice), Daniel (news presenter), Matilda (warm adult female).
# "kokoro" is the on-device fallback voice used when the key lacks text_to_speech permission.
LINES = [
    {"id": "alice_open", "kokoro": "bf_emma", "voice": "EXAVITQu4vr4xnSDxMaL", "at": ("lab_wide", 0.45), "caption": True,
     "text": "Numbers don't lie. But people do. And one changed number can cost a whole community.",
     "settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35}},
    {"id": "alice_whisper", "user_file": "vo/alice_whisper_user.wav", "kokoro": "bf_emma", "speed": 0.9, "voice": "EXAVITQu4vr4xnSDxMaL", "at": ("s4_usb", 3.7), "caption": True,
     "text": "That's not what the log says.", "gain_db": -4,
     "settings": {"stability": 0.3, "similarity_boost": 0.8, "style": 0.6}},
    {"id": "news", "kokoro": "bm_george", "speed": 1.1, "voice": "onwK4e9ZLuTAKqWW03F9", "at": ("s6_amb1", 0.2), "caption": False, "gain_db": -2,
     "text": "Dozens of students near the Taman Harapan industrial estate have been treated for breathing problems.",
     "settings": {"stability": 0.6, "similarity_boost": 0.8, "style": 0.1}, "fx": "broadcast"},
    {"id": "teacher", "kokoro": "af_nova", "speed": 1.1, "say": "Enchik Tan, it's Mei Ling. She can't breathe. We're sending her to the hospital.", "voice": "XrExE9yKIg1WjnnlVkGX", "at": ("s6_call", 0.35), "caption": True,
     "text": "Encik Tan, it's Mei Ling. She can't breathe. We're sending her to the hospital.",
     "settings": {"stability": 0.3, "similarity_boost": 0.8, "style": 0.5}, "fx": "phone"},
    {"id": "alice_close", "kokoro": "bf_emma", "speed": 0.92, "voice": "EXAVITQu4vr4xnSDxMaL", "at": ("s8_close", 0.4), "caption": False,
     "text": "One honest report could have protected every child in that school.",
     "settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.3}},
]


def kokoro(line):
    out = VO / f"{line['id']}.wav"
    subprocess.run(["npx", "hyperframes", "tts", line.get("say", line["text"]), "-v", line["kokoro"], "-s", str(line.get("speed", 1.0)),
                    "-o", str(out)], check=True, capture_output=True)
    # word timings from ElevenLabs Scribe (speech-to-text is allowed on this key)
    r = subprocess.check_output(["curl", "-s", "-X", "POST", "https://api.elevenlabs.io/v1/speech-to-text",
                                 "-F", "model_id=scribe_v1", "-F", f"file=@{out}", "-F", "timestamps_granularity=word"])
    d = json.loads(r)
    ws = [w for w in d.get("words", []) if w.get("type") == "word"]
    words = [{"text": w["text"], "start": w["start"], "end": w["end"]} for w in ws]
    script = line["text"].split()
    extra = len(words) - len(script)
    if extra > 0:  # Scribe split a word the script has as one (e.g. "Encik" -> "And Chick"): merge from the front
        words = [{"text": "", "start": words[0]["start"], "end": words[extra]["end"]}] + words[extra + 1:]
    if len(script) == len(words):  # captions use the script's spelling, Scribe's timing
        for w, t in zip(words, script):
            w["text"] = t
    return out, words


def tts(line):
    body = {"text": line["text"], "model_id": "eleven_multilingual_v2", "voice_settings": line["settings"]}
    out = subprocess.check_output([
        "curl", "-s", "-X", "POST",
        f"https://api.elevenlabs.io/v1/text-to-speech/{line['voice']}/with-timestamps?output_format=mp3_44100_128",
        "-H", "Content-Type: application/json", "-d", json.dumps(body)])
    d = json.loads(out)
    if "audio_base64" not in d:
        return None
    (VO / f"{line['id']}.mp3").write_bytes(base64.b64decode(d["audio_base64"]))
    return d["alignment"]


def words_from_alignment(al):
    words, cur, st = [], "", None
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if ch == " ":
            if cur:
                words.append({"text": cur, "start": st, "end": prev_e})
            cur, st = "", None
            continue
        if st is None:
            st = s
        cur += ch
        prev_e = e
    if cur:
        words.append({"text": cur, "start": st, "end": prev_e})
    return words


def groups(words, at, max_words=6):
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        if w["text"][-1] in ".?!," and len(cur) >= 2 or len(cur) >= max_words or i == len(words) - 1:
            out.append({"start": round(at + cur[0]["start"] - 0.05, 3), "end": round(at + cur[-1]["end"] + 0.15, 3),
                        "text": " ".join(x["text"] for x in cur)})
            cur = []
    return out


def main():
    VO.mkdir(parents=True, exist_ok=True)
    plan = []
    for line in LINES:
        if line.get("user_file"):  # the actor's own recording replaces the generated voice
            plan.append(json.loads((VO / "vo_plan.json").read_text())[[l["id"] for l in LINES].index(line["id"])])
            continue
        al = tts(line)
        if al is not None:
            f, words, engine = VO / f"{line['id']}.mp3", words_from_alignment(al), "elevenlabs"
        else:
            (f, words), engine = kokoro(line), "kokoro"
        at = round(TL[line["at"][0]]["out_start"] + line["at"][1], 3)
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                             "csv=p=0", str(f)]).decode())
        plan.append({"id": line["id"], "file": f"vo/{f.name}", "engine": engine, "start": at, "duration": round(dur, 3),
                     "gain_db": line.get("gain_db", 0), "fx": line.get("fx"),
                     "captions": groups(words, at) if line["caption"] else []})
        print(f"  {line['id']:<14} at {at:7.2f}s  len {dur:5.2f}s  [{engine}]")
    (VO / "vo_plan.json").write_text(json.dumps(plan, indent=1))


if __name__ == "__main__":
    main()
