"""네이버 클립용 세로 영상(1080x1920)을 만든다: AI 음성 + 단어 단위 자막 + 배경음 + 움직이는 사진.

입력: $P/clip/clip.json (장면별 사진·내레이션·상단 문구)
출력: $P/clip/clip.mp4, $P/clip/cover.jpg

사용법: python3 make_clip.py posts/<폴더> [--voice ko-KR-SunHiNeural] [--rate +6%]

clip.json 예:
{
  "voice": "fr-FR-VivienneMultilingualNeural", "rate": "+0%",
  "badge": "광고 · 쇼핑커넥트",
  "scenes": [
    {"photo": "photos/photo_01.jpg", "headline": "히터 전기세\\n한 달 8천원대?",
     "say": "히터 살 때 전기세부터 걱정되시죠?", "highlight": ["전기세"]},
    ...
  ]
}
- photo: 글 폴더 기준 경로. fit(기본, 사진 전체가 보이게) 또는 "mode": "cover"(화면 꽉 채움)
- headline: 화면 위쪽 큰 문구(줄바꿈 \\n, 2줄 이내). say: 읽어 줄 문장. highlight: 자막에서 노란색으로 칠할 말
"""

import argparse
import asyncio
import json
import math
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS, SR = 1080, 1920, 30, 44100
SKILL = Path(__file__).resolve().parent.parent
FONT_DIR = SKILL / "assets" / "fonts"
FONT_URLS = {
    "kr700.ttf": "https://fonts.gstatic.com/s/notosanskr/v40/PbyxFmXiEBPT4ITbgNA5Cgms3VYcOA-vvnIzzg01eLTq9n4g.ttf",
    "kr900.ttf": "https://fonts.gstatic.com/s/notosanskr/v40/PbyxFmXiEBPT4ITbgNA5Cgms3VYcOA-vvnIzzkM1eLTq9n4g.ttf",
}
YELLOW = (255, 214, 64)
ACCENT = (255, 112, 67)
GAP = 0.35          # 장면 사이 쉼(초)
FADE = 0.3          # 장면 전환(초)


def ensure_fonts():
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in FONT_URLS.items():
        p = FONT_DIR / name
        if not p.exists() or p.stat().st_size < 100000:
            subprocess.run(["curl", "-sSfL", "-o", str(p), url], check=True)


def font(weight, size):
    return ImageFont.truetype(str(FONT_DIR / f"kr{weight}.ttf"), size)


# ---------- 음성 ----------
async def tts_one(text, voice, rate, out_mp3):
    import edge_tts
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary", proxy=proxy)
    words, audio = [], bytearray()
    async for ch in com.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            words.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]))
    Path(out_mp3).write_bytes(bytes(audio))
    return words


def decode(mp3):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


# ---------- 배경음(직접 합성, 저작권 걱정 없음) ----------
def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def make_bgm(seconds, seed=0):
    rng = np.random.default_rng(seed)
    bpm = 88
    beat = 60 / bpm
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    progs = [
        [[53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [48, 52, 55, 59]],   # Fmaj7 Em7 Dm7 Cmaj7
        [[57, 60, 64, 67], [53, 57, 60, 64], [48, 52, 55, 59], [55, 59, 62, 65]],   # Am7 Fmaj7 Cmaj7 G7
    ]
    prog = progs[seed % len(progs)]
    bar = beat * 4

    def env(length, a, r):
        k = np.arange(length) / SR
        e = np.minimum(1, k / a) * np.minimum(1, (length / SR - k) / r)
        return np.clip(e, 0, 1)

    def place(sig, start):
        s = int(start * SR)
        if s >= n:
            return
        e = min(n, s + len(sig))
        out[s:e] += sig[: e - s]

    nbars = int(math.ceil(seconds / bar)) + 1
    for b in range(nbars):
        chord = prog[b % 4]
        st = b * bar
        L = int((bar + 0.6) * SR)
        k = np.arange(L) / SR
        pad = np.zeros(L, dtype=np.float32)
        for note in chord:
            f = midi(note)
            for det in (-0.08, 0.08):
                ph = 2 * np.pi * f * (1 + det / 100) * k
                pad += (np.sin(ph) + 0.18 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)).astype(np.float32)
        pad *= env(L, 0.35, 0.6) * 0.018
        place(pad, st)
        # 베이스
        for bt in (0, 2.5):
            Lb = int(beat * 1.4 * SR)
            kb = np.arange(Lb) / SR
            f = midi(chord[0] - 12)
            bass = (np.sin(2 * np.pi * f * kb) * np.exp(-kb * 2.2)).astype(np.float32) * 0.09
            place(bass, st + bt * beat)
        # 아르페지오(퉁기는 소리)
        arp = [chord[0] + 12, chord[2] + 12, chord[3] + 12, chord[1] + 24, chord[2] + 12, chord[3] + 12, chord[1] + 12, chord[2] + 12]
        for i, note in enumerate(arp):
            Lp = int(0.7 * SR)
            kp = np.arange(Lp) / SR
            f = midi(note)
            pl = (np.sin(2 * np.pi * f * kp) + 0.3 * np.sin(4 * np.pi * f * kp)) * np.exp(-kp * 6)
            place((pl * 0.028 * (0.8 + 0.2 * rng.random())).astype(np.float32), st + i * beat / 2)
        # 드럼
        for bt in range(4):
            tb = st + bt * beat
            if bt in (0, 2):
                Lk = int(0.3 * SR)
                kk = np.arange(Lk) / SR
                fk = 45 + 70 * np.exp(-kk * 25)
                kick = np.sin(2 * np.pi * np.cumsum(fk) / SR) * np.exp(-kk * 9)
                place((kick * 0.16).astype(np.float32), tb)
            else:
                Ls = int(0.18 * SR)
                ks = np.arange(Ls) / SR
                sn = rng.standard_normal(Ls) * np.exp(-ks * 22)
                sn = np.convolve(sn, np.ones(6) / 6, mode="same")
                place((sn * 0.035).astype(np.float32), tb)
            for half in (0, 0.5):
                Lh = int(0.05 * SR)
                hh = rng.standard_normal(Lh) * np.exp(-np.arange(Lh) / SR * 80)
                hh = hh - np.convolve(hh, np.ones(4) / 4, mode="same")
                place((hh * 0.03).astype(np.float32), tb + half * beat)
    # 부드럽게: 간단한 저역 통과
    y = np.convolve(out, np.ones(3) / 3, mode="same")
    y = np.convolve(y, np.ones(3) / 3, mode="same").astype(np.float32)
    fade_in = np.minimum(1, t / 0.8)
    fade_out = np.minimum(1, (seconds - t) / 1.8)
    return (y * fade_in * np.clip(fade_out, 0, 1)).astype(np.float32)


# ---------- 그림 ----------
def rounded(img, r):
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), r, fill=255)
    img = img.convert("RGBA")
    img.putalpha(m)
    return img


def prep_scene(path, mode):
    im = Image.open(path).convert("RGB")
    # 배경: 화면을 꽉 채운 흐린 사진
    s = max(W / im.width, H / im.height)
    bg = im.resize((int(im.width * s) + 2, int(im.height * s) + 2), Image.LANCZOS)
    l, tp = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((l, tp, l + W, tp + H))
    if mode == "cover":
        return {"mode": "cover", "full": im, "bg": bg}
    bg = bg.filter(ImageFilter.GaussianBlur(38))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (12, 12, 16)), 0.45)
    # 앞 사진: 가로 1000, 세로 최대 900 (위 문구·아래 자막과 겹치지 않게)
    fw = 1000
    fh = int(im.height * fw / im.width)
    if fh > 900:
        fh = 900
        fw = int(im.width * fh / im.height)
    big = im.resize((int(fw * 1.08), int(fh * 1.08)), Image.LANCZOS)
    return {"mode": "fit", "bg": bg, "big": big, "fw": fw, "fh": fh}


def scene_frame(sc, p, idx):
    """p: 장면 안 진행률 0~1"""
    zoom = 1.0 + 0.07 * p
    if sc["mode"] == "cover":
        im = sc["full"]
        s = max(W / im.width, H / im.height) * (1.04 + 0.06 * p)
        w2, h2 = int(im.width * s), int(im.height * s)
        dx = (w2 - W) * (0.5 + (0.12 if idx % 2 else -0.12) * (p - 0.5))
        dy = (h2 - H) / 2
        frame = im.resize((w2, h2), Image.BILINEAR).crop((int(dx), int(dy), int(dx) + W, int(dy) + H))
        shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(shade)
        for y in range(0, 520):
            d.line([(0, y), (W, y)], fill=(0, 0, 0, int(150 * (1 - y / 520))))
        for y in range(1250, H):
            d.line([(0, y), (W, y)], fill=(0, 0, 0, int(190 * (y - 1250) / (H - 1250))))
        return Image.alpha_composite(frame.convert("RGBA"), shade)
    frame = sc["bg"].copy().convert("RGBA")
    big = sc["big"]
    fw, fh = sc["fw"], sc["fh"]
    cw, ch = int(fw * 1.08 / zoom), int(fh * 1.08 / zoom)
    pan = (0.5 + (0.15 if idx % 2 else -0.15) * (p - 0.5))
    cx = int((big.width - cw) * pan)
    cy = (big.height - ch) // 2
    fg = big.crop((cx, cy, cx + cw, cy + ch)).resize((fw, fh), Image.BILINEAR)
    fg = rounded(fg, 36)
    x = (W - fw) // 2
    y = 950 - fh // 2
    sh = Image.new("RGBA", (fw + 60, fh + 60), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((30, 40, fw + 30, fh + 40), 40, fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(18))
    frame.alpha_composite(sh, (x - 30, y - 30))
    frame.alpha_composite(fg, (x, y))
    return frame


def text_layer(lines, fnt, fill, stroke, stroke_fill, highlights=(), hl_fill=YELLOW, line_gap=14, box=None):
    """여러 줄 글자를 가운데 정렬로 그린 RGBA 레이어. highlights 안의 말은 hl_fill 색."""
    asc, desc = fnt.getmetrics()
    lh = asc + desc
    widths = [fnt.getlength(l) for l in lines]
    tw = int(max(widths)) + stroke * 2 + 40
    th = lh * len(lines) + line_gap * (len(lines) - 1) + stroke * 2 + 20
    layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, line in enumerate(lines):
        x = (tw - widths[i]) / 2
        y = 10 + stroke + i * (lh + line_gap)
        if box:
            pad = 18
            d.rounded_rectangle((x - pad, y - 6, x + widths[i] + pad, y + lh + 4), 16, fill=box)
        marks = [False] * len(line)
        for h in highlights:
            for m in re.finditer(re.escape(h), line):
                for k in range(m.start(), m.end()):
                    marks[k] = True
        # 글자 조각별로 색 바꿔 그리기
        start = 0
        while start < len(line):
            end = start
            while end < len(line) and marks[end] == marks[start]:
                end += 1
            seg = line[start:end]
            sx = x + fnt.getlength(line[:start])
            d.text((sx, y), seg, font=fnt, fill=hl_fill if marks[start] else fill,
                   stroke_width=stroke, stroke_fill=stroke_fill)
            start = end
    return layer


def wrap(text, fnt, maxw):
    out = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            t = (cur + " " + word).strip()
            if fnt.getlength(t) <= maxw or not cur:
                cur = t
            else:
                out.append(cur)
                cur = word
        out.append(cur)
    return out


def chunk_words(words, max_chars=15):
    """단어 타이밍을 자막 덩어리로 묶는다."""
    chunks, cur = [], []
    for w in words:
        cand = " ".join(x[2] for x in cur + [w])
        short_tail = re.search(r"[.?!,]$", w[2]) and len(w[2]) <= 3   # "원." 같은 꼬리는 앞에 붙인다
        if cur and len(cand) > max_chars and not (short_tail and len(cand) <= max_chars + 4):
            chunks.append(cur)
            cur = [w]
        else:
            cur.append(w)
        if re.search(r"[.?!,]$", w[2]) and len(" ".join(x[2] for x in cur)) >= 6:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    res = []
    for i, c in enumerate(chunks):
        st = c[0][0]
        en = chunks[i + 1][0][0] if i + 1 < len(chunks) else c[-1][1] + 0.25
        txt = " ".join(x[2] for x in c)
        txt = re.sub(r"\s+([,.?!])", r"\1", txt).rstrip(",.")
        res.append((st, en, txt))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("post_dir")
    ap.add_argument("--voice")
    ap.add_argument("--rate")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    P = Path(a.post_dir)
    C = P / "clip"
    cfg = json.loads((C / "clip.json").read_text(encoding="utf-8"))
    voice = a.voice or cfg.get("voice", "fr-FR-VivienneMultilingualNeural")
    rate = a.rate or cfg.get("rate", "+0%")
    seed = a.seed if a.seed is not None else sum(map(ord, P.name)) % 7
    ensure_fonts()
    work = C / "_work"
    work.mkdir(parents=True, exist_ok=True)

    # 1) 장면별 음성 + 단어 타이밍
    scenes = cfg["scenes"]
    t = 0.25
    voice_track = []
    for i, sc in enumerate(scenes):
        mp3 = work / f"v{i:02d}.mp3"
        words = asyncio.run(tts_one(sc["say"], voice, rate, mp3))
        pcm = decode(mp3)
        dur = len(pcm) / SR
        sc["_start"], sc["_voice"] = t, dur
        sc["_end"] = t + dur + GAP
        sc["_subs"] = [(t + s, t + e, txt) for s, e, txt in chunk_words(words)]
        voice_track.append((t, pcm))
        t = sc["_end"]
    total = t + 0.6
    print(f"장면 {len(scenes)}개, 길이 {total:.1f}초")

    # 2) 소리 섞기: 음성 + 배경음(말할 때 작게)
    n = int(total * SR)
    vt = np.zeros(n, dtype=np.float32)
    talk = np.zeros(n, dtype=np.float32)
    for st, pcm in voice_track:
        s = int(st * SR)
        vt[s:s + len(pcm)] += pcm[: n - s]
        talk[s:s + len(pcm)] = 1
    k = int(0.25 * SR)
    talk = np.convolve(talk, np.ones(k) / k, mode="same")
    bgm = make_bgm(total, seed)
    gain = 0.55 - 0.33 * talk
    mix = vt / (np.abs(vt).max() + 1e-6) * 0.85 + bgm / (np.abs(bgm).max() + 1e-6) * gain * 0.65
    mix = mix / (np.abs(mix).max() + 1e-6) * 0.9
    wav = work / "mix.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((mix * 32767).astype(np.int16).tobytes())

    # 3) 장면 준비
    for sc in scenes:
        sc["_img"] = prep_scene(P / sc["photo"], sc.get("mode", "fit"))
        sc["_head"] = None
        if sc.get("headline"):
            f = font(900, 78)
            lines = wrap(sc["headline"], f, 900)[:3]
            sc["_head"] = text_layer(lines, f, (255, 255, 255), 0, (0, 0, 0),
                                     highlights=sc.get("headline_highlight", []), hl_fill=(255, 255, 255),
                                     box=(0, 0, 0, 0))
            # 강조 상자 버전
            sc["_head"] = text_layer(lines, f, (20, 20, 24), 0, (0, 0, 0), box=(255, 255, 255, 235),
                                     highlights=sc.get("headline_highlight", []), hl_fill=ACCENT, line_gap=22)
    sub_font = font(900, 64)
    sub_cache = {}

    def sub_layer(txt, hls):
        key = (txt, tuple(hls))
        if key not in sub_cache:
            lines = wrap(txt, sub_font, 940)[:2]
            sub_cache[key] = text_layer(lines, sub_font, (255, 255, 255), 7, (0, 0, 0), highlights=hls)
        return sub_cache[key]

    badge_txt = cfg.get("badge", "광고 · 쇼핑커넥트")
    bf = font(700, 30)
    bw = int(bf.getlength(badge_txt)) + 40
    badge = Image.new("RGBA", (bw, 56), (0, 0, 0, 0))
    ImageDraw.Draw(badge).rounded_rectangle((0, 0, bw - 1, 55), 28, fill=(0, 0, 0, 140))
    ImageDraw.Draw(badge).text((20, 9), badge_txt, font=bf, fill=(255, 255, 255))

    def render(tt):
        i = 0
        while i + 1 < len(scenes) and tt >= scenes[i]["_end"]:
            i += 1
        sc = scenes[i]
        span = sc["_end"] - sc["_start"]
        p = min(1, max(0, (tt - sc["_start"]) / span))
        fr = scene_frame(sc["_img"], p, i)
        if i > 0 and tt - sc["_start"] < FADE:
            prev = scenes[i - 1]
            pf = scene_frame(prev["_img"], 1.0, i - 1)
            fr = Image.blend(pf, fr, (tt - sc["_start"]) / FADE)
        # 상단 문구(올라오며 나타남)
        if sc["_head"] is not None:
            q = min(1, (tt - sc["_start"]) / 0.35)
            lay = sc["_head"]
            if q < 1:
                lay = lay.copy()
                alpha = lay.getchannel("A").point(lambda v: int(v * q))
                lay.putalpha(alpha)
            y = 470 - lay.height + int(30 * (1 - q))
            fr.alpha_composite(lay, ((W - lay.width) // 2, y))
        # 자막
        for s, e, txt in sc["_subs"]:
            if s <= tt < e:
                lay = sub_layer(txt, sc.get("highlight", []))
                fr.alpha_composite(lay, ((W - lay.width) // 2, 1440))
                break
        fr.alpha_composite(badge, (40, 70))
        # 진행 막대
        d = ImageDraw.Draw(fr)
        d.rectangle((0, 0, int(W * tt / total), 8), fill=ACCENT)
        return fr.convert("RGB")

    out = C / "clip.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
           "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    nf = int(total * FPS)
    for f in range(nf):
        proc.stdin.write(render(f / FPS).tobytes())
        if f % 150 == 0:
            print(f"  {f}/{nf}", flush=True)
    proc.stdin.close()
    proc.wait()
    render(min(1.2, scenes[0]["_end"] - 0.1)).save(C / "cover.jpg", quality=90)
    up = cfg.get("upload")
    if up:
        tags = " ".join("#" + h.lstrip("#") for h in up.get("hashtags", []))
        (C / "upload.txt").write_text(f"[제목]\n{up['title']}\n\n[설명]\n{up['description']}\n\n[해시태그]\n{tags}\n",
                                      encoding="utf-8")
    print(out, f"{out.stat().st_size / 1e6:.1f}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
