"""
Drum extraction (Phase 3): noise channel, DPCM samples and pitch-drop "drums" (P1 / P2 / TRI).

Noise and DPCM hits are mapped to General MIDI percussion note numbers (v0.1.23: written on the
NES channel's own MIDI channel, noise = ch 4, DPCM = ch 5; v0.1.22 and before: ch 10).
Pitch-drop drums keep their original pitch and stay on their channel (P1 / P2 / TRI = ch 1-3,
own tracks; v0.1.20-0.1.22: ch 11-13).

Noise
  Hit start: hi reg ($400F) write while audible, silence -> sound, or a volume
  jump of >= NOISE_REATTACK (drivers that re-hit by rewriting the volume only).
  A hit lasts until silence or the next hit. Many drivers sweep the period
  during a hit (e.g. Mega Man 2 snare 11,0,5,10,15), so the classification uses
  the volume-weighted average period index, the hit length and the peak volume.
  The kind of a hit is keyed by its first-frame (period index, mode) so it can be
  remapped from the command line (--drum-map "3:0=42,12:0=36").

DPCM
  Each sample start is a hit. The sample bytes are decoded (1-bit delta) and the
  zero-crossing rate after a 40 Hz high-pass gives a rough brightness:
    < 1200 Hz : kick (short) / low tom (long)
    < 4500 Hz : snare
    otherwise : hi-hat (short) / open hi-hat
  Looping samples are treated as tonal samples and skipped.
  v0.1.23: a sample (address, length) played at more than one rate is a pitched sample: its
  hits get a pitch from the rate (dmc_rate_pitch) and their own track, so the melody is kept.
  v0.1.24: the pitch comes from the waveform: the period of the decoded sample in bits
  (dpcm_period, autocorrelation) and the rate give the real frequency. Samples without a clear
  period (drums played at several rates) start at PITCHED_FALLBACK_LOW for their lowest rate.

Pitch-drop drums (v0.1.20: also on the pulse channels)
  Short notes (<= TRI_DRUM_MAX frames) that glide down by >= DROP_DRUM_MIN
  semitones (option --drop-drums): the classic "triangle kick", and pulse toms
  (e.g. Balloon Fight, Wrecking Crew: 4 frames, one octave down). They keep
  their pitch; the gm field (36 / 45) is only a hint for the console report.
  v0.1.21: the pitch must keep falling from the start (is_glide). A melody note
  that steps down once and holds, or falls only at its end (glissando into the
  next note, e.g. Gradius II), is not a drum.
"""

import math

from apu_state import DMC_RATE_NTSC
from notes import find_gate_end

GM_NAMES = {
    35: "Acoustic Bass Drum", 36: "Bass Drum", 37: "Side Stick", 38: "Snare", 39: "Hand Clap",
    40: "Electric Snare", 41: "Low Floor Tom", 42: "Closed Hi-Hat", 43: "High Floor Tom",
    44: "Pedal Hi-Hat", 45: "Low Tom", 46: "Open Hi-Hat", 47: "Low-Mid Tom", 48: "Hi-Mid Tom",
    49: "Crash Cymbal", 50: "High Tom", 51: "Ride Cymbal", 56: "Cowbell", 57: "Crash Cymbal 2",
}

NOISE_REATTACK = 3
TRI_DRUM_MAX = 12
DROP_DRUM_MIN = 3       # default minimum fall in semitones (--drop-drums; 0 = off). v0.1.20 and before: 5
GLIDE_TOL = 0.5         # semitones: smaller frame-to-frame changes count as "flat"


class DrumHit:
    __slots__ = ("src", "start", "end", "gm", "vel", "kind", "info", "note", "pitch")

    def __init__(self, src, start, end, gm, vel, kind, info="", note=None, pitch=None):
        self.src = src          # "NOI" / "DMC" / "P1" / "P2" / "TRI" (the last three: pitch-drop drums)
        self.start = start
        self.end = end
        self.gm = gm
        self.vel = vel
        self.kind = kind        # key used for remapping / reporting
        self.info = info
        self.note = note        # pitch-drop drums: the original Note (pitch, peak volume)
        # MIDI note to write instead of gm: pitch-drop drums (original pitch), pitched DPCM samples
        self.pitch = note.pitch if pitch is None and note is not None else pitch


def _vel(v):
    return max(1, min(127, int(round(v * 127 / 15))))


# ------------------------------------------------------------------ noise
def classify_noise(w_idx, dur, mode):
    if w_idx <= 4.5:
        if dur <= 5:
            return 42
        return 46 if dur <= 12 else 49
    if w_idx < 9.5:
        return 38 if dur <= 20 else 49
    return 36 if dur <= 8 else 41


def noise_hits(frames, drum_map=None):
    hits = []
    cur = None
    prev_vol = 0

    def close(at):
        nonlocal cur
        if cur is None:
            return
        f0, key, data = cur
        vols = [v for _, v in data]
        # ignore a low reverb tail (DQ2 holds the noise at volume 1) when measuring the hit
        g = find_gate_end(vols)
        data = data[:g]
        vols = vols[:g]
        tot = sum(vols) or 1
        w_idx = sum(p * v for p, v in data) / tot
        dur = min(at - f0, g)
        gm = classify_noise(w_idx, dur, key[1])
        if drum_map and key in drum_map:
            gm = drum_map[key]
        hits.append(DrumHit("NOI", f0, f0 + dur, gm, _vel(max(vols)), key,
                            f"idx {key[0]} mode {key[1]} avg {w_idx:.1f} {dur}f"))
        cur = None

    for fr in frames:
        n = fr["state"]["NOI"]
        vol = n["vol"]
        trig = 3 in fr["written"]["NOI"]
        f = fr["frame"]
        if vol == 0:
            close(f)
            prev_vol = 0
            continue
        if cur is None or trig or vol - prev_vol >= NOISE_REATTACK:
            close(f)
            cur = (f, (n["period_idx"], n["mode"]), [])
        if f - cur[0] < 60:
            cur[2].append((n["period_idx"], vol))
        prev_vol = vol
    close(len(frames))
    return hits


# ------------------------------------------------------------------- DPCM
def dpcm_decode(data, dac=64):
    out = []
    for byte in data:
        for i in range(8):
            if (byte >> i) & 1:
                if dac <= 125:
                    dac += 2
            elif dac >= 2:
                dac -= 2
            out.append(dac)
    return out


def dpcm_brightness(data, rate_hz):
    sig = dpcm_decode(data)
    if len(sig) < 16:
        return 0.0, 0.0
    win = max(2, int(rate_hz / 40))
    s = 0.0
    prev = None
    z = 0
    for i, v in enumerate(sig):
        s += v
        if i >= win:
            s -= sig[i - win]
        hp = v - s / min(i + 1, win)
        if prev is not None and (hp < 0) != (prev < 0):
            z += 1
        prev = hp
    dur = len(sig) / rate_hz
    return z / 2 / dur, dur


def classify_dpcm(freq, dur):
    if freq < 1200:
        return 36 if dur < 0.12 else 45
    if freq < 4500:
        return 38
    return 42 if dur < 0.08 else 46


PERIOD_MIN_AC = 0.5          # autocorrelation needed to trust the estimated period
PITCHED_FALLBACK_LOW = 48    # no clear period: the lowest rate of the sample becomes this note
_period_cache = {}


def dmc_rate_pitch(rate, cpu_hz, period=32.0):
    """MIDI note (float) of a sample whose waveform repeats every `period` bits, played at `rate`.
    period 32 = the rate table's own tuning (rate 0 = C3 ... rate 15 = C6)."""
    hz = cpu_hz / DMC_RATE_NTSC[rate] / period
    return 69 + 12 * math.log2(hz / 440.0)


def dpcm_period(data):
    """Period of the decoded sample in bits (autocorrelation), or None if it has no clear period.
    The first peak reaching 90% of the highest one is taken (prefers the fundamental over its
    multiples; the octave can still be off by one). Needs numpy (None without it)."""
    key = bytes(data)
    if key in _period_cache:
        return _period_cache[key]
    res = None
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None and len(data) >= 8:
        x = np.array(dpcm_decode(data[:1024]), float)
        n = len(x)
        w = min(1024, n)
        x = x - np.convolve(x, np.ones(w) / w, "same")
        x -= x.mean()
        ac = np.correlate(x, x, "full")[n - 1:]
        if ac[0] > 0:
            ac = ac / ac[0]
            hi = min(n // 2, 1200)
            peaks = [k for k in range(16, hi) if ac[k] > ac[k - 1] and ac[k] >= ac[k + 1]]
            top = max((ac[k] for k in peaks), default=0)
            if top >= PERIOD_MIN_AC:
                k = next(k for k in peaks if ac[k] >= 0.9 * top)
                a, b, c = ac[k - 1], ac[k], ac[k + 1]
                den = a - 2 * b + c
                res = k + (0.5 * (a - c) / den if den else 0.0)   # parabolic peak refinement
    _period_cache[key] = res
    return res


def dmc_hits(frames, samples, cpu_hz, drum_map=None):
    hits = []
    prev = None
    cache = {}
    for fr in frames:
        d = fr["state"]["DMC"]
        if prev is not None and d["starts"] != prev:
            key = (d["addr"], d["len"], d["rate"])
            if d["loop"]:
                prev = d["starts"]
                continue
            if key not in cache:
                rate_hz = cpu_hz / DMC_RATE_NTSC[d["rate"]]
                data = samples.get((d["addr"], d["len"]), b"")
                freq, dur = dpcm_brightness(data, rate_hz)
                cache[key] = (classify_dpcm(freq, dur), freq, dur)
            gm, freq, dur = cache[key]
            dkey = ("DMC", d["addr"], d["len"], d["rate"])
            if drum_map and dkey in drum_map:
                gm = drum_map[dkey]
            frames_len = max(1, int(round(dur * 60)))
            hits.append(DrumHit("DMC", fr["frame"], fr["frame"] + frames_len, gm, 110, dkey,
                                f"${d['addr']:04X} len {d['len']} rate {d['rate']} ~{freq:.0f}Hz {dur * 1000:.0f}ms"))
        prev = d["starts"]
    # the DMC plays one sample at a time: a new sample start cuts the previous one
    for h, nxt in zip(hits, hits[1:]):
        h.end = max(h.start + 1, min(h.end, nxt.start))
    # the same sample at several rates = pitched sample (unless remapped with --drum-map)
    rates = {}
    for h in hits:
        rates.setdefault(h.kind[1:3], set()).add(h.kind[3])
    shift = {}
    for key, rs in rates.items():
        if len(rs) < 2:
            continue
        period = dpcm_period(samples.get(key, b""))
        if period:
            shift[key] = (period, 0.0, True)
        else:   # no clear period: keep the intervals of the rates, lowest rate = PITCHED_FALLBACK_LOW
            shift[key] = (32.0, PITCHED_FALLBACK_LOW - dmc_rate_pitch(min(rs), cpu_hz), False)
    for h in hits:
        key = h.kind[1:3]
        if key in shift and not (drum_map and h.kind in drum_map):
            period, off, found = shift[key]
            h.pitch = max(0, min(127, int(round(dmc_rate_pitch(h.kind[3], cpu_hz, period) + off))))
            h.info += f" period {period:.1f} bits" if found else " no clear period"
    return hits


# --------------------------------------------------------------- pitch-drop drums
DROP_DRUM_CHANNELS = ("P1", "P2", "TRI")


def is_glide(ps, min_drop):
    """True if the per-frame pitches fall by >= min_drop and keep falling from the start:
    never rise, fall within the first two frames, and fall on at least half of the frames."""
    if len(ps) < 2 or ps[0] - min(ps) < min_drop:
        return False
    steps = [b - a for a, b in zip(ps, ps[1:])]
    if any(s > GLIDE_TOL for s in steps):
        return False
    if steps[0] > -GLIDE_TOL and (len(steps) < 2 or steps[1] > -GLIDE_TOL):
        return False
    return 2 * sum(1 for s in steps if s < -GLIDE_TOL) >= len(steps)


DETECT_TRI_DROP = 5.0  # fixed triangle-kick rule for the detection inputs (see detect_triangle_split)


def detect_triangle_split(tri_notes):
    """The fixed v0.1.19 triangle-kick rule (<= TRI_DRUM_MAX frames, falls >= 5 semitones).

    Used only for the tempo / meter / loop detection inputs, so that they do not depend on
    --drop-drums (changing which notes count as drums broke loop detection in some songs)."""
    tonal, hits = [], []
    for n in tri_notes:
        ps = [p for p in n.pitches if p is not None]
        if ps and n.end - n.start <= TRI_DRUM_MAX and ps[0] - min(ps) >= DETECT_TRI_DROP:
            hits.append(DrumHit("TRI", n.start, n.end, 36, 110, ("TRI",), "", n))
        else:
            tonal.append(n)
    return tonal, hits


def split_drop_drums(ch_notes, src, min_drop=DROP_DRUM_MIN):
    """Split one channel (P1 / P2 / TRI) into (tonal_notes, drum_hits). min_drop <= 0: off."""
    if min_drop <= 0:
        return ch_notes, []
    tonal, hits = [], []
    for n in ch_notes:
        length = n.end - n.start
        ps = [p for p in n.pitches if p is not None]
        if ps and length <= TRI_DRUM_MAX and is_glide(ps, min_drop):
            gm = 36 if min(ps) < 60 else 45
            vel = 110 if src == "TRI" else _vel(n.peak)
            hits.append(DrumHit(src, n.start, n.end, gm, vel, (src,),
                                f"glide {ps[0]:.0f}->{min(ps):.0f}", n))
        else:
            tonal.append(n)
    return tonal, hits


def parse_drum_map(text):
    """'3:0=42,12:0=36,DMC:E000:129:15=38' -> {key: gm}."""
    out = {}
    if not text:
        return out
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        k, v = item.split("=")
        parts = k.split(":")
        if parts[0].upper() == "DMC":
            key = ("DMC", int(parts[1], 16), int(parts[2]), int(parts[3]))
        else:
            key = (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        out[key] = int(v)
    return out


def summarize(hits):
    """Per kind: (count, gm, example info, pitch) for the console report.
    pitch: the MIDI note of a pitched DPCM sample, else None."""
    table = {}
    for h in hits:
        t = table.setdefault((h.src, h.kind), [0, {}, h.info, h.pitch])
        t[0] += 1
        t[1][h.gm] = t[1].get(h.gm, 0) + 1
    out = []
    for (src, kind), (cnt, gms, info, pitch) in sorted(table.items(), key=lambda x: -x[1][0]):
        gm = max(gms, key=gms.get)
        out.append((src, kind, cnt, gm, info, pitch if src == "DMC" else None))
    return out
