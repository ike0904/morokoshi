"""
Tempo detection from frame-exact note onsets.

NES music drivers advance on whole frames, so onsets fall on a regular grid of
`unit` frames (the finest row). Drivers with a tempo accumulator (e.g. Dragon
Quest) produce fractional units such as 14.4 frames (onsets on round(k * 14.4));
grooves such as 6,7,6,7 give 6.5.

1. Grid search (detect_grid): unit candidates 2..48 frames on a geometric scale
   (0.2 % steps) plus all integer / half units. Phase by circular mean. Score is
   the share of onsets within tolerance, corrected for chance:
       norm = (hit - chance) / (1 - chance),  chance = 2 * tol / unit
   The largest unit whose norm is within NORM_MARGIN of the best is chosen.
2. Rows per beat (choose_rows): if most inter-onset intervals are a multiple of
   3 units the music is ternary (triplets / shuffle) -> 12, 6, 3 or 24 rows per
   beat, otherwise 4, 2, 8 or 16; first candidate giving BPM in [BPM_LO, BPM_HI).
3. Tempo map (detect_tempo_map): the global grid is checked in windows of
   WINDOW_SEC; windows it does not fit get their own grid; consecutive windows
   with the same unit are merged into segments; boundaries are refined per onset.
"""

import math
from bisect import bisect_left
from collections import Counter

BPM_LO = 70.0
BPM_HI = 170.0
NORM_MARGIN = 0.08
WINDOW_SEC = 8.0
FIT_OK = 0.85
LOCAL_MIN = 0.6     # a window gets its own grid if it fits at least this well
LOCAL_GAIN = 0.25   # ... and beats the global grid by this margin
MERGE_RATIO = 0.03  # neighbouring segments closer than this are merged
PHRASE_GAP_ROWS = 6 # a gap this long (in rows) before an onset is a phrase break


def _tol(unit):
    # rounding of accumulator drivers is <= 0.5 frame; a little slack for phase error
    return min(0.75, unit * 0.2)


def _hits(onsets, unit, phase):
    tol = _tol(unit)
    out = []
    for o in onsets:
        d = (o - phase) % unit
        if d > unit / 2:
            d -= unit
        out.append(abs(d) <= tol)
    return out


def _phase(onsets, unit):
    two_pi = 2.0 * math.pi
    sx = sy = 0.0
    for o in onsets:
        a = two_pi * (o / unit)
        sx += math.cos(a)
        sy += math.sin(a)
    return (math.atan2(sy, sx) / two_pi) * unit % unit


DRIFT_WINDOW = None     # v0.1.38: frames; set while detecting a SPC tune (detect_tempo_map(drift=True))


def _drift_hits(onsets, unit):
    """Hits with the phase taken per DRIFT_WINDOW: the tempo of SPC drivers wanders by a few
    frames over a minute (FF4 "Red Wings": 27.0-27.5 frames per beat), so one phase for the
    whole tune misses most notes of a fine grid."""
    hits = 0
    i = 0
    while i < len(onsets):
        j = i
        while j < len(onsets) and onsets[j] < onsets[i] + DRIFT_WINDOW:
            j += 1
        sub = onsets[i:j]
        hits += sum(_hits(sub, unit, _phase(sub, unit)))
        i = j
    return hits


def _fit(onsets, unit):
    phase = _phase(onsets, unit)
    if DRIFT_WINDOW and onsets[-1] - onsets[0] > DRIFT_WINDOW:
        score = _drift_hits(onsets, unit) / len(onsets)
    else:
        score = sum(_hits(onsets, unit, phase)) / len(onsets)
    chance = min(0.999, 2 * _tol(unit) / unit)
    norm = (score - chance) / (1 - chance)
    return score, norm, phase


def _candidates(min_unit, max_unit):
    out = set(i / 2 for i in range(int(min_unit * 2), int(max_unit * 2) + 1))
    u = float(min_unit)
    while u <= max_unit + 1e-9:
        out.add(u)
        u *= 1.002
    return sorted(out, reverse=True)


def detect_grid(onsets, min_unit=2.0, max_unit=48.0):
    onsets = sorted(set(onsets))
    if len(onsets) < 4:
        return None
    results = [(u,) + _fit(onsets, u) for u in _candidates(min_unit, max_unit)]
    best = max(r[2] for r in results)
    for u, score, norm, phase in results:          # descending unit order
        if norm >= best - NORM_MARGIN:
            # local refinement absorbs accumulator drift; keep u unless clearly better
            fine = [(v,) + _fit(onsets, v) for v in (u * (1 + k * 0.0004) for k in range(-6, 7))]
            v = max(fine, key=lambda r: r[2])
            if v[2] > norm + 0.01:
                u, score, norm, phase = v
            # snap to an exact integer / half unit when it fits as well
            snap = round(u * 2) / 2
            if snap != u and abs(snap - u) / u < 0.002:
                s2 = _fit(onsets, snap)
                if s2[0] >= score - 0.005:
                    u, (score, norm, phase) = snap, s2
            # v0.1.28: short tunes leave the unit loose (Wrecking Crew t5: 8.083 for an exact
            # 8-frame grid); take the whole number of frames when it fits every onset as well
            snap = round(u)
            if snap != u and abs(snap - u) / u < 0.02:
                s2 = _fit(onsets, snap)
                if s2[0] >= score:
                    u, (score, norm, phase) = snap, s2
            return {"unit": u, "score": score, "norm": norm, "phase": phase}
    return None


def is_ternary(onsets, unit):
    onsets = sorted(set(onsets))
    iois = [round((b - a) / unit) for a, b in zip(onsets, onsets[1:])]
    iois = [i for i in iois if i > 0]
    if not iois:
        return False
    div3 = sum(1 for i in iois if i % 3 == 0)
    return div3 / len(iois) > 0.5


SHUFFLE_PAIRS = 0.45   # share of consecutive interval pairs that are long-short (2:1) or short-long
SHUFFLE_MIN_ONSETS = 8 # v0.1.28 (16 before): short jingles in shuffle (Wrecking Crew t5: 13 onsets)


def shuffle_step(onsets, unit):
    """Shuffle / swing written on a straight grid: consecutive intervals alternate
    long-short in a 2:1 ratio (2s, s). Returns s (in grid units) or None.

    Examples: Super Mario Bros. 3 - grid 6 frames, intervals 12,6,12,6 (s = 1 unit, 86 % of
    the pairs); Super Mario USA - grid 2 frames, intervals 12,6 (s = 3 units, 54 %).
    Plain runs of equal notes, dotted rhythms (3:1) or 8th+16th figures do not qualify.
    """
    onsets = sorted(set(onsets))
    if len(onsets) < SHUFFLE_MIN_ONSETS:
        return None
    iois = [round((b - a) / unit) for a, b in zip(onsets, onsets[1:])]
    pairs = list(zip(iois, iois[1:]))
    if not pairs:
        return None
    best, best_s = 0.0, None
    for step in range(1, 13):
        hit = sum(1 for a, b in pairs if (a, b) in ((2 * step, step), (step, 2 * step)))
        share = hit / len(pairs)
        if share > best:
            best, best_s = share, step
    if best < SHUFFLE_PAIRS or shuffle_lattice(onsets, unit, best_s) < SHUFFLE_LATTICE:
        return None
    return best_s


SHUFFLE_LATTICE = 0.8    # v2.9.30: share of the onsets on the long-short positions of the beat
SHUFFLE_WINDOW = 32      # onsets per window (the phase is taken per window)


def shuffle_lattice(onsets, unit, step):
    """v2.9.30: in a shuffle the onsets sit on the two positions of the long-short beat (0 and 2s
    of 3s); 16th-8th-16th syncopations on a straight beat also alternate 1:2 and 2:1, but their
    onsets fall anywhere in a 3s cycle. Share of the onsets on the two positions, the phase taken
    per SHUFFLE_WINDOW onsets.
    470 tunes: real shuffles 0.84-1.00 (Super Mario Bros. 3 t1 0.91, Wrecking Crew t1 0.92),
    straight tunes 0.69-0.73 (Adventure Island 3 t1 0.70: 6-frame 16ths, 150 BPM, was 200 shuffle)."""
    period = 3 * step
    hit = tot = 0
    for i in range(0, len(onsets), SHUFFLE_WINDOW):
        w = onsets[i:i + SHUFFLE_WINDOW]
        if len(w) < 4:
            continue
        pos = [round((o - w[0]) / unit) for o in w]
        hit += max(sum(1 for p in pos if (p - ph) % period in (0, 2 * step)) for ph in range(period))
        tot += len(w)
    return hit / tot if tot else 0.0


TRIPLET_REP_GAIN = 0.15   # pitches repeat after 3 notes clearly more often than after 4 ...
TRIPLET_FIT_GAIN = 0.05   # ... and the notes line up on a 3-note beat better than on a 4-note beat


def triplet_note(channel_notes, force=False):
    """Triplet feel written as plain notes: the most common note interval d is a triplet 8th
    (1 beat = 3d). Looks at each channel separately, because merged onsets of a 2:1 bass and a
    triplet melody form an even grid. Returns d (frames) or None.

    Examples: The Legend of Zelda overworld - bass 24,8,8,8 frames with 16ths (6 frames) in the
    melody (grid 2 frames), Clu Clu Land t3 - 16,8 bass under triplet runs (grid 8 frames).
    channel_notes: {ch: {start frame: pitch}}. force=True returns d without the check.
    """
    chans = [c for c in channel_notes.values() if len(c) >= 16]
    iois = Counter()
    for c in chans:
        st = sorted(c)
        iois.update(b - a for a, b in zip(st, st[1:]) if b - a >= 4)
    if not iois:
        return None
    d = iois.most_common(1)[0][0]
    if force:
        return d
    rep, fit = {}, {}
    for k in (3, 4):
        period = k * d
        hit = tot = 0
        fits = []
        for c in chans:
            for f, p in c.items():
                tot += 1
                # the same pitch one or two periods later (within a frame)
                if any(c.get(f + m * period + e) == p for m in (1, 2) for e in (-1, 0, 1)):
                    hit += 1
            fits.append(beat_fit(sorted(c), period, tol=1.0)[0])
        rep[k] = hit / tot
        fit[k] = sum(fits) / len(fits)
    if rep[3] - rep[4] >= TRIPLET_REP_GAIN and fit[3] - fit[4] >= TRIPLET_FIT_GAIN:
        return d
    return None


SEXT_MIN_NOTES = 12     # v0.1.38: long notes needed to call the beat 6 rows instead of 8 ...
SEXT_GAIN = 0.2         # ... when they line up on 6 rows clearly better than on 8 ...
SEXT_FIT = 0.6          # ... and well on 6 rows


def sextuplet_beat(channel_notes, unit):
    """v0.1.38: a grid of 6 rows per beat on a binary-looking grid: triplet 8ths (2 rows) and
    sextuplets (1 row) with 8ths (3 rows) and quarters (6 rows). The intervals are mostly even
    numbers of rows, so is_ternary says binary and the beat became 8 rows (FF4 "Red Wings":
    4.5-frame grid, 99 BPM). The long notes (>= 6 rows to the next note of the channel: melody,
    cymbals) decide: the gaps between them are multiples of 6 rows, not of 8. Notes within a frame of the grid
    count (SPC drivers' tempo rounding)."""
    longs = []
    for c in (channel_notes or {}).values():
        st = sorted(c)
        longs += [a for a, b in zip(st, st[1:]) if b - a >= 6 * unit - 1]
    longs = sorted(set(round(x, 1) for x in longs))
    # the gaps between them (not one phase over the tune: the tempo of a SPC driver drifts
    # by a few frames over a minute)
    rows = []
    for x, y in zip(longs, longs[1:]):
        r = round((y - x) / unit)
        if r > 0 and abs(y - x - r * unit) <= 1.0:
            rows.append(r)
    if len(rows) < SEXT_MIN_NOTES:
        return False
    six = sum(1 for r in rows if r % 6 == 0) / len(rows)
    eight = sum(1 for r in rows if r % 8 == 0) / len(rows)
    return six >= SEXT_FIT and six - eight >= SEXT_GAIN


BAR_REPEAT = 0.85       # v0.1.35: share of a section's onsets that come again one bar later
BAR_MIN_ONSETS = 12
BAR_REPEAT_WALK = 0.7   # ... when following the figure to the end of the section (a slowing bar misses some)


def _repeat_share(onsets, idx, lo, hi, lag, min_n=BAR_MIN_ONSETS):
    sel = [o for o in onsets if lo <= o < hi and o + lag < hi]
    if len(sel) < min_n:
        return 0.0, len(sel)
    hit = 0
    for o in sel:
        i = bisect_left(onsets, o + lag - 1.0)
        if i < len(onsets) and onsets[i] <= o + lag + 1.0:
            hit += 1
    return hit / len(sel), len(sel)


def bar_period(onsets, lo, hi, unit, frame_rate):
    """A section (a later tempo segment) whose figure repeats bar by bar: the shortest lag (whole
    grid units, a multiple of 4 = one 4/4 bar) at which BAR_REPEAT of its onsets come again,
    giving a tempo of 70-240 BPM. Returns (lag in units, first onset of the repeating figure,
    start of the last bar = the bar after the last repeat, grid unit measured over the bars) or None. The section start moves back to where the figure starts repeating (the window-based
    segmentation finds it a little late).
    Example: Dragon Quest III t26 - from frame 8100 the same 16th figure every 106.7 frames
    (32 units of 3.33) = one bar of 135 BPM, after 100 BPM (it was 89.9 BPM, 2.67 beats a bar)."""
    if hi == float("inf"):
        hi = onsets[-1] + 1
    for lag_units in range(8, 129):
        lag = lag_units * unit
        share, n = _repeat_share(onsets, None, lo, hi, lag)
        if share < BAR_REPEAT:
            continue
        if lag_units % 4:
            return None
        bpm = 60.0 * frame_rate * 4 / lag
        if not BPM_LO <= bpm < 240.0:
            return None
        def repeats(o, need=BAR_REPEAT):     # the figure starting at onset o comes again a bar later
            sh, m = _repeat_share(onsets, None, o, o + 2 * lag, lag, 4)
            i = bisect_left(onsets, o + lag - 1.0)
            return sh >= need and i < len(onsets) and onsets[i] <= o + lag + 1.0
        # earliest onset (up to one bar before lo) from which the figure keeps repeating
        start = lo
        for o in [x for x in onsets if lo - lag <= x < lo]:
            if repeats(o):
                start = o
                break
        # the figure repeats bar by bar from `start`; the bar after the last repeat is the last
        # one of the section (Dragon Quest III t26: the 8th bar slows down into the intro tempo)
        f, bars = start, 0
        while f + lag < hi + 2 * lag and repeats(f, BAR_REPEAT_WALK):
            f = min(onsets[bisect_left(onsets, f + lag - 1.0):][:1] or [f + lag])   # follow the onsets
            bars += 1
        # the grid unit from the bars themselves (the window estimate drifts by half a row over
        # 7 bars: 3.338 instead of 3.330 frames)
        if bars >= 2:
            unit = (f - start) / (bars * lag_units)
        return lag_units, start, f, unit
    return None


def _on_grid(d, unit, tol=0.75):
    r = d / unit
    return abs(r - round(r)) * unit <= tol


def _section_handover(onsets, bar_start, unit, downbeat, next_unit):
    """Where the next section's tempo takes over inside the last bar of a repeating section:
    the earliest onset from which every onset up to the next downbeat sits on the next
    section's grid (counted back from the downbeat) while the ones before it sit on this
    section's grid. Dragon Quest III t26: the last fast bar plays its figure for 3 beats, then
    G C D in triplets of the intro tempo lead into the long G (the slowing-down of bar 64)."""
    cand = [o for o in onsets if bar_start <= o <= downbeat]
    for i, c in enumerate(cand):
        if all(_on_grid(o - bar_start, unit) for o in cand[:i]) and                 all(_on_grid(downbeat - o, next_unit) for o in cand[i:]):
            return c
    return downbeat


def melody_onsets(channel_notes):
    """v0.1.33: note starts of the melody = the channel with the highest notes (at least 16 notes).
    The 8th-note rule of choose_rows looks at the melody, not at all channels merged: running
    accompaniment in 16ths would otherwise count as 8ths (Dragon Quest III t26: bass / pulse in
    9-frame 16ths, melody mostly 18-frame 8ths -> 100 BPM, not 200)."""
    chans = {ch: c for ch, c in (channel_notes or {}).items() if len(c) >= 16}
    if not chans:
        return None
    mel = max(chans, key=lambda ch: sorted(chans[ch].values())[len(chans[ch]) // 2])
    return sorted(chans[mel])


def choose_rows(unit, frame_rate, ternary, prefer_bpm=None, onsets=None):
    family = (12, 6, 3, 24) if ternary else (4, 2, 8, 16)
    if prefer_bpm:
        # keep continuity with the previous segment
        return min(family, key=lambda m: abs(math.log((60.0 * frame_rate / (unit * m)) / prefer_bpm)))
    if ternary and onsets and len(onsets) > 8:
        # the most common interval is an 8th note (half a beat), if that gives a sane tempo
        # (Super Mario Bros.: grid 3 frames, mostly 9-frame 8ths -> 6 rows/beat = 200 BPM,
        # triplets are 6 frames = 2 rows). v0.1.33: the onsets of the melody (melody_onsets)
        iois = Counter(round((b - a) / unit) for a, b in zip(onsets, onsets[1:]))
        mode = max((i for i in iois if i > 0), key=lambda i: iois[i], default=0)
        m = 2 * mode
        if m in family and BPM_LO <= 60.0 * frame_rate / (unit * m) < 240.0:
            return m
    for m in family:
        bpm = 60.0 * frame_rate / (unit * m)
        if BPM_LO <= bpm < BPM_HI:
            return m
    return family[0]


def beat_fit(onsets, period, tol=0.75):
    """Best-phase grid fit (exhaustive over onset residues, unlike the circular mean this
    works for multi-modal patterns such as shuffles). Returns (norm, score, phase)."""
    if not onsets:
        return 0.0, 0.0, 0.0
    res = [o % period for o in onsets]
    best = (0, 0.0)
    for ph in set(round(r * 4) / 4 for r in res):
        hit = 0
        for r in res:
            d = abs(r - ph)
            if min(d, period - d) <= tol:
                hit += 1
        if hit > best[0]:
            best = (hit, ph)
    score = best[0] / len(onsets)
    chance = min(0.999, 2 * tol / period)
    return (score - chance) / (1 - chance), score, best[1]


PULSE_NORM = 0.4      # v0.1.42: the long notes line up on the pulse at least this well ...
PULSE_FRAMES = (18.0, 51.0)   # ... searched over this range (frames at 60 Hz)
PULSE_LONG = 10       # a note followed by this many frames (60 Hz) in its channel is a long note
PULSE_WINDOW = 10.0   # seconds per window of the fit
RHYTHM_NORM = 0.6     # v2.9.28: the triangle + drums alone line up on the same pulse at least this well ...
RHYTHM_SAME = 0.01    # ... (within this share of the period): the beat of a tune without a loop


def _residue_fit(onsets, period, tol=1.0):
    """beat_fit with a sliding window over the sorted residues (fast; same norm)."""
    res = sorted(o % period for o in onsets)
    n = len(res)
    ext = res + [r + period for r in res]
    best = 0
    j = 0
    for i in range(n):
        if j < i:
            j = i
        while j < i + n and ext[j] <= ext[i] + 2 * tol:
            j += 1
        best = max(best, j - i)
    score = best / n
    chance = min(0.999, 2 * tol / period)
    return (score - chance) / (1 - chance)


def note_pulse(channel_notes, frame_rate, drum_onsets=None):
    """v0.1.42: the period (frames) on which the long notes of all channels line up best: the beat
    or half / double of it. Unlike the grid search this works for triplets that the driver
    rounds to whole frames (7, 7, 6 frames in a 20-frame beat: Minna no Taabou t1, Super Spike
    V'Ball t2; 9, 9, 6 in 24: Super Team Games t1), and it finds the beat when the fine grid
    divides it in a way choose_rows does not expect (a 4-frame grid with a 24-frame beat:
    Elnark no Zaihou t3, Ganbare Pennant Race t1). Returns (period, norm) or None."""
    k = frame_rate / 60.0
    longs = set()
    # drums count as channels of their own (kick / snare mark the beat: Ikinari Musician t2 is
    # mostly drums)
    for c in list((channel_notes or {}).values()) + list((drum_onsets or {}).values()):
        st = sorted(set(c))
        longs.update(a for a, b in zip(st, st[1:]) if b - a >= PULSE_LONG * k)
    longs = sorted(longs)
    if len(longs) < 24:
        return None
    # the fit per window of PULSE_WINDOW seconds, averaged: a period 0.01 frame off drifts by a
    # whole frame over a long tune (Super Spike V'Ball t2: 19.82 frames, 3 minutes)
    win = PULSE_WINDOW * frame_rate
    parts, cur = [], []
    for o in longs:
        if cur and o >= cur[0] + win:
            parts.append(cur)
            cur = []
        cur.append(o)
    parts.append(cur)
    parts = [x for x in parts if len(x) >= 8] or [longs]

    def scan(fit):
        best = None
        p = PULSE_FRAMES[0] * k
        while p <= PULSE_FRAMES[1] * k:
            nm = fit(p)
            if best is None or nm > best[1] + 1e-9:
                best = (p, nm)
            p += 0.1 * k
        return best
    # over the whole tune first; per window only when that finds nothing
    best = scan(lambda p: _residue_fit(longs, p))
    if best[1] >= PULSE_NORM or len(parts) < 2:
        return best
    best = scan(lambda p: sum(_residue_fit(x, p) * len(x) for x in parts) / sum(len(x) for x in parts))
    # the exact period over the whole tune
    # (the middle of the periods that fit best: with a 1-frame tolerance a range of them ties)
    p0 = best[0]
    qs = [p0 + i * 0.001 * k for i in range(-60, 61)]
    fits = [_residue_fit(longs, q) for q in qs]
    top = max(fits)
    tied = [q for q, f in zip(qs, fits) if f >= top - 1e-9]
    return tied[len(tied) // 2], best[1]


def _ioi_share(channel_notes, u):
    """Share of the note intervals (per channel, at least 4 frames) that are a whole number of
    grid rows u (within a frame)."""
    hit = tot = 0
    for c in (channel_notes or {}).values():
        st = sorted(c)
        for a, b in zip(st, st[1:]):
            d = b - a
            if d >= 4:
                tot += 1
                hit += abs(d - round(d / u) * u) <= 1.0
    return hit / tot if tot else 0.0


def _pulse_grid(onsets, frame_rate, g, pulse, channel_notes=None, hi=BPM_HI):
    """v0.1.42: the grid and rows per beat from the pulse when the detected grid does not divide
    it. Returns (unit, rows, ternary) or None."""
    P = pulse
    best = None
    cands = []
    for kk in (2, 3, 4, 6, 8, 12, 16):
        if P / kk < 2.0:
            break
        # the pulse is only known to about a frame: the best grid near P / kk (+-0.3 %)
        sc, u = max((_fit(onsets, v)[0], v) for v in (P / kk * (1 + i * 0.0004) for i in range(-8, 9)))
        if abs(u - g["unit"]) / g["unit"] < 0.003 and g["score"] >= sc - 0.005:
            # the detected grid when it is this one (exact: Kkachi-Wa Norae Chingu 8.0133 frames)
            sc, u = g["score"], g["unit"]
        else:
            # a whole, half or third of a frame when it fits as well (drivers count whole frames)
            for snap in sorted({round(u), round(u * 2) / 2, round(u * 3) / 3}, key=lambda v: abs(v - u)):
                if snap >= 2.0 and abs(snap - u) / u < 0.003:
                    s2 = _fit(onsets, snap)[0]
                    if s2 >= sc - 0.005:
                        sc, u = s2, snap
                        break
        # the coarsest grid that explains the onsets about as well as the finest
        if best is None or sc > best[1] + 0.03:
            best = (u, sc, kk)
        cands.append((u, sc, kk))
    if best is not None and channel_notes:
        # of the grids about as good as the chosen one, the one the note intervals are made of
        # (Tom & Jerry t1: 10 / 5-frame notes - 2.5 frames, not the triplet 3.33 of a 20-frame pulse)
        near = [c for c in cands if c[1] >= best[1] - 0.03]
        if len(near) > 1:
            share = {c[2]: _ioi_share(channel_notes, c[0]) for c in near}
            top = max(share.values())
            best = next(c for c in near if share[c[2]] >= top - 0.02)
    # the detected grid itself when the pulse is a whole number of its rows (Ikinari Musician t2:
    # 2-frame grid of arpeggios, pulse 20 frames)
    n = pulse / g["unit"]
    if round(n) >= 2 and abs(n - round(n)) < 0.05 and (best is None or best[1] < g["score"] - 0.03):
        best = (g["unit"], g["score"], round(n))
    if best is None:
        return None
    u, sc, kk = best
    # as well as the detected grid (Ikinari Musician t2: 1-2 frame arpeggios leave every grid
    # near 76 %), and well in absolute terms when the detected grid fitted well
    if sc < min(0.85, g["score"] - 0.03):
        return None
    ternary = kk % 3 == 0 and kk % 4 != 0 and kk % 5 != 0
    rows = kk
    # the pulse may be half a beat: binary music keeps BPM_LO..BPM_HI, triplets up to 240
    hi = 240.0 if ternary else hi
    while 60.0 * frame_rate / (u * rows) >= hi:
        rows *= 2
    while 60.0 * frame_rate / (u * rows) < BPM_LO and rows % 2 == 0:
        rows //= 2
    return u, rows, ternary


class Segment:
    def __init__(self, start, unit, phase, score):
        self.start = start      # first onset frame belonging to the segment
        self.unit = unit
        self.phase = phase
        self.score = score
        self.rows = 4
        self.bpm = 0.0

    def __repr__(self):
        return f"Segment(start={self.start}, unit={self.unit:.4g}, bpm={self.bpm:.2f}, fit={self.score:.2f})"


def detect_tempo_map(onsets, frame_rate, rows_per_beat=None, unit=None, channel_notes=None, triplets="auto",
                     tempo="auto", drift=False, drum_onsets=None, loop_period=None):
    """drift=True (SPC, v0.1.38): grid fits take the phase per few seconds (_drift_hits)."""
    global DRIFT_WINDOW
    DRIFT_WINDOW = 4.0 * frame_rate if drift else None
    try:
        return _detect_tempo_map(onsets, frame_rate, rows_per_beat, unit, channel_notes, triplets, tempo,
                                 drum_onsets, loop_period)
    finally:
        DRIFT_WINDOW = None


def _detect_tempo_map(onsets, frame_rate, rows_per_beat=None, unit=None, channel_notes=None, triplets="auto",
                      tempo="auto", drum_onsets=None, loop_period=None):
    """triplets: "auto" (detect), "on" (always triplet feel) or "off" (always binary).
    tempo: "auto", "half" (rows per beat x2) or "double" (rows per beat /2, only where the rows are even).
    Applied per segment after detection, so segments / triplets / shuffle are still detected."""
    onsets = sorted(set(onsets))
    if len(onsets) < 4:
        return None
    if unit:
        sc, nm, ph = _fit(onsets, unit)
        g = {"unit": unit, "score": sc, "norm": nm, "phase": ph}
        segs = [Segment(onsets[0], unit, ph, sc)]
    else:
        g = detect_grid(onsets)
        segs = _segment(onsets, frame_rate, g)
    ternary = is_ternary(onsets, g["unit"])
    step = None if rows_per_beat else shuffle_step(onsets, g["unit"])
    shuffle = step is not None
    if shuffle:
        ternary = True
    trip_d = None
    if triplets == "off":
        ternary, shuffle = False, False
    elif not rows_per_beat and not ternary:
        trip_d = triplet_note(channel_notes or {}, force=triplets == "on")
        # (SPC only: on NES tunes it changed Tom & Jerry and T&C Surf Designs, unchecked)
        ternary = bool(trip_d) or triplets == "on" or bool(DRIFT_WINDOW and sextuplet_beat(channel_notes, g["unit"]))
    prev = None
    for s in segs:
        if rows_per_beat:
            s.rows = rows_per_beat
        elif trip_d and prev is None:
            # 1 beat = 3 triplet notes; double / halve into a sane tempo
            s.rows = max(1, round(3 * trip_d / s.unit))
            while 60.0 * frame_rate / (s.unit * s.rows) >= 240.0:
                s.rows *= 2
            while s.rows % 2 == 0 and 60.0 * frame_rate / (s.unit * s.rows) < BPM_LO:
                s.rows //= 2
        elif shuffle and prev is None:
            # 1 beat = one long-short pair (2s + s); double it if that would exceed 240 BPM
            s.rows = 3 * step if 60.0 * frame_rate / (s.unit * 3 * step) < 240.0 else 6 * step
        else:
            s.rows = None
            if prev is not None and not DRIFT_WINDOW:
                # v0.1.35: a new section whose figure repeats bar by bar takes its tempo from it
                k = segs.index(s)
                end = segs[k + 1].start if k + 1 < len(segs) else float("inf")
                per = bar_period(onsets, s.start, end, s.unit, frame_rate)
                if per:
                    lag_units, start, last_bar, s.unit = per
                    sec_end = last_bar + lag_units * s.unit
                    if k + 1 < len(segs) and segs[k + 1].start < sec_end - 1:
                        nxt = [o for o in onsets if o >= sec_end - 1]
                        if nxt and (k + 2 >= len(segs) or nxt[0] < segs[k + 2].start):
                            segs[k + 1].start = _section_handover(onsets, last_bar, s.unit,
                                                                  nxt[0], segs[k + 1].unit)
                            segs[k + 1].start_fixed = True      # keep it, no jump to a bar line
                    # the shortest repeat may be half a bar: of one / two repeats per bar, the
                    # tempo nearer to the previous section (Dragon Quest III t26: back to 100 BPM
                    # after 135, its figure repeats every 2 beats)
                    s.rows = min((lag_units // 4, lag_units // 2),
                                 key=lambda r: abs(math.log(60.0 * frame_rate / (s.unit * r) / prev)))
                    if start < s.start and (k == 0 or start > segs[k - 1].start)                             and not getattr(s, "start_fixed", False):
                        s.start = start
            if not s.rows:
                s.rows = choose_rows(s.unit, frame_rate, ternary, prev, melody_onsets(channel_notes) or onsets)
        s.bpm = 60.0 * frame_rate / (s.unit * s.rows)
        prev = s.bpm
    # v0.1.42: the beat must line up with the pulse of the long notes (1/2, 1 or 2 pulses);
    # otherwise the grid and the beat come from the pulse (one tempo for the tune only).
    # v0.1.43: only for tunes with a loop, and only when the new beat makes the loop a whole
    # number of 4/4 bars (a check the tune itself gives; 480 tunes: tempos of tunes without a
    # loop changed by 3/2, 4/3 ... with nothing to tell which is right)
    # v2.9.28 (user: "the triangle or the rhythm gives it"): a tune without a loop too, when the
    # triangle and the drums alone line up on the same pulse; that pulse is the beat (up to 240 BPM).
    # Tom & Jerry & Tuffy t1, Balda (BBG) t1: 20 frames = 180 BPM (135 / 112.7 before)
    pulse = False
    if (not rows_per_beat and not unit and not DRIFT_WINDOW and len(segs) == 1 and triplets != "off"):
        pl = note_pulse(channel_notes, frame_rate, drum_onsets) if loop_period else None
        rhythm = False
        if not loop_period:
            pl = note_pulse(channel_notes, frame_rate, drum_onsets)
            rh = note_pulse({"TRI": (channel_notes or {}).get("TRI", {})}, frame_rate, drum_onsets) if pl else None
            rhythm = bool(rh and rh[1] >= RHYTHM_NORM and abs(rh[0] / pl[0] - 1) < RHYTHM_SAME)
            if not rhythm:
                pl = None
        s = segs[0]
        if pl and pl[1] >= PULSE_NORM:
            beat = s.unit * s.rows
            if not any(abs(beat / (pl[0] * m) - 1) < 0.03 for m in (0.5, 1, 2)):
                pg = _pulse_grid(onsets, frame_rate, g, pl[0], channel_notes, 240.0 if rhythm else BPM_HI)
                if pg and loop_period:
                    beats = loop_period / (pg[0] * pg[1])
                    if abs(beats - round(beats)) > 0.1 or round(beats) % 4:
                        pg = None
                if pg:
                    s.unit, s.rows, ternary = pg
                    s.score, _, s.phase = _fit(onsets, s.unit)
                    s.bpm = 60.0 * frame_rate / (s.unit * s.rows)
                    g = {"unit": s.unit, "score": s.score, "norm": _fit(onsets, s.unit)[1], "phase": s.phase}
                    shuffle, trip_d, pulse = False, None, True
                    # the rhythm section keeps one steady beat: no tempo tracking on the poor fit
                    # of the fine grid (Tom & Jerry t1 swayed 135-152 BPM)
                    s.steady = rhythm
    kept = 0  # segments left as detected ("double" on an odd number of rows, e.g. 3 rows per beat)
    if not rows_per_beat and tempo in ("half", "double"):
        for s in segs:
            if tempo == "half":
                s.rows *= 2
            elif s.rows % 2 == 0:
                s.rows //= 2
            else:
                kept += 1
            s.bpm = 60.0 * frame_rate / (s.unit * s.rows)
    return {"drift": bool(DRIFT_WINDOW), "tempo_kept": kept, "global": g, "segments": segs, "ternary": ternary, "shuffle": shuffle, "triplet": bool(trip_d), "pulse": pulse}


def _segment(onsets, frame_rate, g):
    win = frame_rate * WINDOW_SEC
    t0 = onsets[0]
    windows = []
    i = 0
    while i < len(onsets):
        w0 = t0 + len(windows) * win
        sub = []
        while i < len(onsets) and onsets[i] < w0 + win:
            sub.append(onsets[i])
            i += 1
        windows.append(sub)
    # v0.1.41: a last window shorter than half a window (the song ends just after a window
    # boundary) joins the one before: a few onsets fit some grid by chance (Ys t8: the last 0.6 s
    # got a tempo of its own, 117.9 BPM)
    if len(windows) >= 2 and windows[-1] and windows[-1][-1] - (t0 + (len(windows) - 1) * win) < win / 2:
        windows[-2].extend(windows.pop())

    # label each window: None = global grid fits, else its own grid
    labels = []
    for sub in windows:
        if len(sub) < 6:
            labels.append(None)
            continue
        ph = _phase(sub, g["unit"])
        gfit = sum(_hits(sub, g["unit"], ph)) / len(sub)
        if gfit >= FIT_OK:
            labels.append(None)
            continue
        lg = detect_grid(sub, max(2.0, g["unit"] / 2.2), min(48.0, g["unit"] * 2.2))
        if (lg and abs(lg["unit"] - g["unit"]) / g["unit"] >= 0.015
                and lg["score"] >= LOCAL_MIN and lg["score"] - gfit >= LOCAL_GAIN
                and not (DRIFT_WINDOW and _multiple(lg["unit"], g["unit"]))):
            labels.append(lg["unit"])
        else:
            labels.append(None)

    # merge runs of equal labels (units within 1.5 %)
    runs = []   # [label, [onsets]]
    for lab, sub in zip(labels, windows):
        if runs and _same(runs[-1][0], lab):
            runs[-1][1].extend(sub)
        else:
            runs.append([lab, list(sub)])
    runs = [r for r in runs if r[1]]

    # merge neighbouring runs whose units differ by < MERGE_RATIO (accumulator drift, not a tempo change)
    merged = []
    for lab, sub in runs:
        u = g["unit"] if lab is None else lab
        if merged:
            pu = g["unit"] if merged[-1][0] is None else merged[-1][0]
            if DRIFT_WINDOW and _multiple(u, pu):      # SPC: the same grid at another level
                if u < pu:
                    merged[-1][0] = lab
                merged[-1][1].extend(sub)
                continue
            if abs(u - pu) / pu < MERGE_RATIO:
                merged[-1][1].extend(sub)
                continue
        merged.append([lab, list(sub)])
    runs = merged

    segs = []
    for lab, sub in runs:
        u = g["unit"] if lab is None else lab
        if DRIFT_WINDOW:        # SPC: the exact tempo of each section (best fit near the unit)
            u = max((v for v in _candidates(u * 0.985, u * 1.015)), key=lambda v: _fit(sub, v)[1])
        elif lab is not None:
            lg = detect_grid(sub, max(2.0, u * 0.95), min(48.0, u * 1.05))
            if lg:
                u = lg["unit"]
        ph = _phase(sub, u)
        sc = _fit(sub, u)[0]          # (v0.1.38: per few seconds for SPC)
        segs.append(Segment(sub[0], u, ph, sc))

    # refine boundaries: move each split to the onset that maximizes total hits
    for k in range(1, len(segs)):
        a, b = segs[k - 1], segs[k]
        lo = b.start - win
        hi = b.start + win
        region = [o for o in onsets if lo <= o < hi and o >= a.start]
        if len(region) < 2:
            continue
        ha = _hits(region, a.unit, a.phase)
        hb = _hits(region, b.unit, b.phase)
        best_j, best_v = None, -1
        scores = []
        for j in range(1, len(region)):
            v = sum(ha[:j]) + sum(hb[j:])
            scores.append((j, v))
            if v > best_v:
                best_j, best_v = j, v
        # Prefer a phrase break (long note / rest before the onset) when it scores nearly as well:
        # a ritardando at the end of a section otherwise drifts onto the next section's grid
        # (Dragon Quest II overture: the 6/8 intro slows down from 13 to 16 frames per 8th,
        # holds a G, and the 4/4 part starts after a 164-frame gap).
        slack = max(3, int(0.3 * len(region)))
        breaks = [(j, v) for j, v in scores
                  if region[j] - region[j - 1] >= PHRASE_GAP_ROWS * a.unit and v >= best_v - slack]
        if breaks:
            best_j = min(breaks, key=lambda jv: abs(jv[0] - best_j))[0]
        b.start = region[best_j]
    # drop segments that became empty or out of order
    clean = []
    for s in segs:
        if clean and s.start <= clean[-1].start:
            continue
        clean.append(s)
    return clean


def _multiple(a, b):
    """v0.1.38 (SPC): a and b are the same grid up to a whole factor and the drift of the driver
    (FF4 "Red Wings" 49 s: triplet 8ths alone, 9.14 frames on a 4.53-frame grid). The window
    keeps the global grid; tempo tracking follows the drift."""
    if a < b:
        a, b = b, a
    k = round(a / b)
    return k >= 1 and abs(a / (k * b) - 1) < MERGE_RATIO


def _same(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) / a < 0.015


TRACK_FIT = 0.9          # segments fitting worse than this are tempo-tracked (rubato / ritardando)
RIT_MIN = 1.045          # v0.1.29: a run of notes this much longer than the channel's usual note ...
RIT_MAX = 1.6            # ... (but not as long as a different note value) ...
RIT_RUN = 3              # ... for this many notes in a row is a ritardando
RIT_STEP = 0.2           # ... changing by at most this x the usual note from note to note ...
RIT_STEP_FRAMES = 2      # ... or (v2.9.28) by this many frames: frame rounding on short notes
PHASE_GAIN = 1.25       # v0.1.33: the downbeat by note weight must beat beat 0 by this much ...
PHASE_MIN_NOTES = 16    # ... over at least this many notes on beats
CONTINUOUS_ROWS = 2      # v0.1.29: a segment starting this close after the last note keeps its natural tick


JITTER_TOL = 1.5        # v0.1.31: frames; onsets this close to the grid ...
JITTER_FIT = 0.9        # ... this often = a steady tempo whose notes are rounded to frames
STEADY_MIN_NOTES = 16   # v0.1.44: a channel with this many notes in a segment ...
STEADY_SPREAD = 0.8     # ... spread over this share of it ...
STEADY_FIT = 0.98       # ... this often on the grid = a steady tempo (steady_channel)


def steady_with_jitter(onsets, unit, phase):
    """A segment that misses the strict grid fit only because every note is rounded to a frame
    (+-1, sometimes 2 frames on a short unit) keeps one steady tempo instead of being tracked
    note by note: tracking drifts across long rests. Rubato drifts away from any grid.
    Example: Dragon Quest IV t13 - 16ths of 5.734 frames, fit 78% at 0.75 frames, 93% at 1.5."""
    if not onsets or unit < 2 * JITTER_TOL:
        return False
    hits = 0
    for o in onsets:
        d = (o - phase) % unit
        if min(d, unit - d) <= JITTER_TOL:
            hits += 1
    return hits / len(onsets) >= JITTER_FIT


def steady_channel(notes, start, end, unit, phase):
    """v0.1.44: a segment keeps one steady tempo when one channel plays on the grid all through it
    (STEADY_FIT of at least STEADY_MIN_NOTES notes spread over the segment): a tempo change would
    move that channel too; the other channels' misses are ornaments off the grid.
    Example: Kkachi-Wa Norae Chingu t1 - the melody's echo notes 7 and 14 frames after its 8ths
    gave a fit of 74 % and a tracked tempo of 119-135 BPM in a tune of 112.69 BPM throughout;
    the chords and the bass stay on the 8-frame grid."""
    if not notes:
        return False
    for lst in notes.values():
        on = [n.start for n in lst if start <= n.start < end]
        if len(on) < STEADY_MIN_NOTES:
            continue
        span = min(end, max(n.end for n in lst)) - max(start, min(on))
        if on[-1] - on[0] < STEADY_SPREAD * span:
            continue
        if sum(_hits(on, unit, phase)) / len(on) >= STEADY_FIT:
            return True
    return False


def has_ritardando(starts, unit):
    """A ritardando inside a segment that still fits its grid: the notes of one channel get
    gradually longer than its usual note (e.g. 19 frames per 8th -> 21, 24, 26, 28, 26, 24, 21),
    so the slow notes round up to extra rows and the bars drift. Runs of one longer value
    (dotted notes: 28, 28, 28) do not count - the lengths must change along the run, step by
    step (no jump of more than 0.2 x the usual note), and grow from the first note of the run
    (a run that only gets shorter is a speed-up into the tempo, e.g. the Airball intro).

    Example: Dragon Quest III t15 - 8ths of 19 frames slow down twice in the loop.
    Final Fantasy III t2 - 16ths of 9-10 frames slow down to 13 in the last bar (11, 13, 12, 13)
    and speed up again in the first; untracked, the 256 notes of the loop took 259 rows (6/8)."""
    st = sorted(starts)
    iois = [b - a for a, b in zip(st, st[1:])]
    if len(iois) < 8:
        return False
    common = Counter(iois).most_common(1)[0][0]
    # the usual note in whole grid rows: accumulator drivers alternate e.g. 5 and 6 frames for
    # a 6.002-frame row (Shatterhand), which must not look like a slow-down
    d = max(1, round(common / unit)) * unit
    if d < 4:
        return False
    step = max(RIT_STEP, RIT_STEP_FRAMES / d)
    run = []
    for i in iois + [0]:
        r = i / d
        if RIT_MIN < r < RIT_MAX:
            run.append(r)
            continue
        if (len(run) >= RIT_RUN and max(run) - min(run) >= 0.05 and any(abs(x - 1.5) > 0.07 for x in run)
                and max(run) >= run[0] + 0.05 and all(abs(b - a) <= step + 1e-9 for a, b in zip(run, run[1:]))):
            return True
        run = []
    return False
COMPOUND_MIN_NOTES = 3
COMPOUND_FIT = 0.85      # long notes on 3-eighth boundaries (dotted-quarter beats) ...
COMPOUND_GAIN = 0.15     # ... clearly more often than on 2-eighth boundaries
REP6_MIN = 0.15          # v0.1.43: the melody comes back after 6 8ths at least this often ...
REP6_RATIO = 2.0         # ... and this many times as often as after 4 or 8
BEAT_PHASE_GAIN = 1.15   # ternary grid: another row starts the beat if it scores this much better (v0.1.28)
BINARY_PHASE_GAIN = 3.0  # v2.9.31: binary grid of a tune without a loop: another row must score this much better
MIXED_TRIPLET_ERR = 1.5  # ternary grid: an onset this many frames off the triplet rows ...
MIXED_16TH_ERR = 0.5     # ... and this close to a 16th of the beat is placed on the 16th (v0.1.28)


def beat_phase(onsets, unit, origin, rows, channels=None, step=None, gain=None):
    """Ternary grids (3 / 6 rows per beat): which row (mod rows) starts the beat. Each onset
    scores the rows until the next onset (capped at one beat): in a shuffle the long note of
    the long-short pair starts on the beat, and longer notes start on beats in general.
    Returns the row offset p (0 = the grid point near frame 0 is a beat), a multiple of rows / 3.

    Example: Wrecking Crew t1 - grid 8 frames from frame -4, 16+8 shuffle from frame 108
    (row 14): the beats are rows 2, 5, 8, ... (p = 2)."""
    score = [0.0] * rows
    # v2.9.28: each channel on its own (channels = onsets per channel): a channel playing the
    # figure of another one a few rows later made the other's notes look short (Bikkuriman World t2:
    # P2 = P1 15 frames later moved the beat into the middle of the 8ths and gave a pickup)
    for lst in (channels or [onsets]):
        pos = [round((o - origin) / unit) for o in lst]
        for a, b in zip(pos, pos[1:] + [None]):
            w = rows if b is None else min(rows, b - a)
            if w > 0:
                score[a % rows] += w
    # only shifts by whole triplet 8ths (a shift by half a beat is a binary question, not handled)
    # v2.9.31: step / gain for the binary grids (BINARY_PHASE_GAIN)
    best = max(range(0, rows, step or rows // 3), key=lambda p: score[p])
    return best if score[best] >= (gain or BEAT_PHASE_GAIN) * score[0] and score[best] > score[0] else 0


def track_rows(onsets, unit, origin):
    """Assign grid rows to onsets while following a slowly changing tempo.

    Returns [(frame, row)] anchors. Each interval is rounded to whole rows with the current
    unit, then the unit is updated from short intervals (<= 4 rows), so a ritardando
    (13, 14, 15, 16 frames per row) keeps every note on its row.
    """
    anchors = []
    u = unit
    f_prev, r_prev = origin, 0
    for i, o in enumerate(onsets):
        if i + 1 < len(onsets) and onsets[i + 1] - o < 0.5 * u:
            continue                    # grace note just before the main note: anchor the main note
        d = o - f_prev
        r = int(round(d / u))
        if r < 1:
            continue                    # grace note / same event
        anchors.append((o, r_prev + r))
        if r <= 4:
            u = 0.5 * u + 0.5 * (d / r)
        f_prev, r_prev = o, r_prev + r
    return anchors


def track_rows_drift(onsets, unit, origin, bar_rows):
    """v0.1.38 (SPC): track_rows for drivers whose notes are exact in tempo but land up to
    ~0.5 frame off (timer ticks) and whose tempo may change by a percent (FF4 "Red Wings").
    The unit is measured over about a bar (from the anchor at least bar_rows back), so the
    jitter of single notes does not move it; one tempo per bar is written as usual."""
    anchors = []
    u = unit
    f_prev, r_prev = origin, 0
    for i, o in enumerate(onsets):
        if i + 1 < len(onsets) and onsets[i + 1] - o < 0.5 * u:
            continue
        r = int(round((o - f_prev) / u))
        if r < 1:
            continue
        r_now = r_prev + r
        anchors.append((o, r_now))
        base = None
        for fa, ra in reversed(anchors[:-1]):
            if r_now - ra >= bar_rows:
                base = (fa, ra)
                break
        if base:
            est = (o - base[0]) / (r_now - base[1])
            if abs(est / u - 1) < 0.05:
                u = 0.7 * u + 0.3 * est
        f_prev, r_prev = o, r_now
    return anchors


class _Part:
    def __init__(self, seg, origin_frame, origin_tick, tpu, anchors, unit_end):
        self.seg = seg
        self.origin_frame = origin_frame
        self.origin_tick = origin_tick
        self.tpu = tpu
        self.anchors = anchors          # [(frame, row)] for tracked parts, [] for steady parts
        self.unit_end = unit_end        # local unit after the last anchor
        self.last_onset = origin_frame
        self.meter = (4, 4)
        self.bar_ticks = 4 * 480
        self.bar_origin = origin_tick   # tick the bar lines count from (after a pickup bar, v0.1.29)
        self.lead_beats = 0             # length of the pickup bar at the start (0 = none)
        self.lead_meter = None          # v0.1.43: meter of a pickup bar in 8ths (6/8 tunes), at lead_tick
        self.lead_tick = 0
        self.short_bar = None           # v2.9.33: (tick, meter) of a short bar before bar_origin (bars before it count from origin_tick)
        self.meter_phase = 0            # v0.1.43: 6/8 bar lines this many 8ths after the grid origin

    def rows_at(self, frame):
        s = self.seg
        if not self.anchors:
            return (frame - self.origin_frame) / s.unit
        pts = [(self.origin_frame, 0)] + self.anchors
        if frame <= pts[0][0]:
            return (frame - pts[0][0]) / s.unit
        for (f0, r0), (f1, r1) in zip(pts, pts[1:]):
            if frame <= f1:
                return r0 + (frame - f0) / (f1 - f0) * (r1 - r0)
        f_last, r_last = pts[-1]
        return r_last + (frame - f_last) / self.unit_end

    def frame_at_row(self, row):
        pts = [(self.origin_frame, 0)] + self.anchors
        for (f0, r0), (f1, r1) in zip(pts, pts[1:]):
            if row <= r1:
                return f0 + (row - r0) / (r1 - r0) * (f1 - f0)
        f_last, r_last = pts[-1]
        return f_last + (row - r_last) * self.unit_end


class TickMap:
    """frame -> MIDI tick through a tempo map of grid segments.

    - steady segments: fixed grid unit (one tempo)
    - segments with a poor grid fit (rubato, ritardando): rows are tracked note by note
      (track_rows) and the timing is kept with tempo events between the anchors
    - meter per segment: 6/8 when long notes sit on dotted-quarter boundaries, else 4/4
    - a new segment starts on the bar line after the last note of the previous one, which
      absorbs fermatas / held notes at section ends; the gap gets its own tempo event so the
      playback timing is unchanged
    """

    def __init__(self, tmap, ppq, quantize=True, frame_rate=60.0, onsets=None, notes=None,
                 meters=None, downbeat=None, loop_period=None):
        self.ppq = ppq
        self.loop = (downbeat, loop_period) if downbeat is not None and loop_period else None
        self.quantize = quantize
        self.fr = frame_rate
        onsets = sorted(set(onsets or []))
        self.onset_set = set(onsets)     # note starts (only they may go on 16ths in a triplet grid)
        self.extra_meters = []
        self.downbeat_tick = None        # tick of the loop start's bar line (_set_downbeat)
        segs = tmap["segments"]
        self.parts = []
        for k, s in enumerate(segs):
            tpu = ppq / s.rows
            end = segs[k + 1].start if k + 1 < len(segs) else float("inf")
            seg_on = [o for o in onsets if (k == 0 or o >= s.start) and o < end]
            if k == 0:
                # keep the leading silence: the song starts at frame 0 (drivers start the sequence
                # on the first PLAY call), so the first grid point at/near frame 0 is tick 0
                origin = s.phase + s.unit * round((0 - s.phase) / s.unit)
                origin_tick = 0
                if s.rows % 3 == 0 and quantize:
                    # v0.1.28: put the beat on the right triplet row; the rows before it become a
                    # rest at the start (frame 0 then sits inside the first beat)
                    chans = [sorted({n.start for n in lst if n.start < end}) for lst in (notes or {}).values()]
                    p = beat_phase(seg_on, s.unit, origin, s.rows, [c for c in chans if c] or None)
                    if p:
                        origin -= (s.rows - p) * s.unit
                elif s.rows % 2 == 0 and s.rows >= 4 and quantize and downbeat is None and notes:
                    # v2.9.31: the same on a binary grid, for a tune without a loop, by 16ths. Pooyan t1:
                    # sound effects for 13.5 s put the grid half a beat off the melody's quarters
                    # (A4 G4 F#4 E4 D4 every 24 frames from frame 811, with the triangle's D3)
                    chans = [sorted({n.start for n in lst if n.start < end}) for lst in notes.values()]
                    p = beat_phase(seg_on, s.unit, origin, s.rows, [c for c in chans if c] or None,
                                   step=s.rows // 4, gain=BINARY_PHASE_GAIN)
                    if p:
                        origin -= (s.rows - p) * s.unit
            else:
                origin = s.start
                if getattr(s, "start_fixed", False):
                    # v0.1.35: section handover inside a bar (bar_period): continue the bar
                    origin_tick = int(round(self._tick_in(self.parts[-1], origin)))
                else:
                    origin_tick = self._bar_after(self.parts[-1], origin)
            anchors, unit_end = [], s.unit
            rit = s.score >= TRACK_FIT and notes is not None and any(
                has_ritardando([n.start for n in lst if (k == 0 or n.start >= s.start) and n.start < end], s.unit)
                for lst in notes.values())
            s.rit = rit
            jitter = s.score < TRACK_FIT and not rit and (
                getattr(s, "steady", False) or
                steady_with_jitter(seg_on, s.unit, s.phase)
                or steady_channel(notes, s.start if k else -1, end, s.unit, s.phase))
            if tmap.get("drift") and len(seg_on) >= 4:
                # v0.1.38 (SPC): always followed bar by bar (tempo drift, small tempo changes)
                anchors = track_rows_drift([o for o in seg_on if o > origin], s.unit, origin, 4 * s.rows)
                if len(anchors) >= 2:
                    (fa, ra), (fb, rb) = anchors[-2], anchors[-1]
                    unit_end = (fb - fa) / (rb - ra)
            elif (s.score < TRACK_FIT and not jitter or rit) and len(seg_on) >= 4:
                anchors = track_rows([o for o in seg_on if o > origin], s.unit, origin)
                if len(anchors) >= 2:
                    (fa, ra), (fb, rb) = anchors[-2], anchors[-1]
                    unit_end = (fb - fa) / (rb - ra)
            part = _Part(s, origin, origin_tick, tpu, anchors, unit_end)
            part.last_onset = seg_on[-1] if seg_on else origin
            if meters and k < len(meters) and meters[k]:
                part.meter = meters[k]
            else:
                part.meter = self._detect_meter(part, notes, end)
            part.bar_ticks = int(round(ppq * 4 * part.meter[0] / part.meter[1]))
            s.meter = part.meter
            s.tracked = bool(anchors)
            if k == 0 and part.meter_phase:
                self._compound_pickup(part, notes, end,
                                      downbeat if downbeat is not None and (len(segs) == 1 or downbeat < segs[1].start)
                                      else None)
            elif k == 0 and downbeat is not None and (len(segs) == 1 or downbeat < segs[1].start):
                self._set_downbeat(part, downbeat)
            elif k == 0 and downbeat is None and quantize and notes:
                self._phase_downbeat(part, notes, end)
            elif k > 0:
                # a segment that starts mid-bar (continuous music, see _bar_after) keeps the
                # previous bar lines; its meter starts at the next bar line
                pb = self.parts[-1]
                rel = origin_tick - pb.bar_origin
                if rel % pb.bar_ticks:
                    part.bar_origin = pb.bar_origin + math.ceil(rel / pb.bar_ticks) * pb.bar_ticks
            self.parts.append(part)

    # ------------------------------------------------------------------ meter
    def _set_downbeat(self, part, frame):
        """v0.1.29: make `frame` (the loop start) a bar line by putting a short bar at the start:
        the beats before it that do not fill whole bars become the first bar (a pickup bar of
        1-3 beats, e.g. 3/4, then 4/4).
        The loop start is rounded to the beat when it lies within a quarter beat of one, else the
        beat before it is taken (the loop often starts on the pickup note just after the beat).
        Examples: Wrecking Crew t1 - loop start 15.67 beats -> 3/4 + 4/4 from beat 3 (the main
        theme starts on a downbeat); Dragon Quest III t15 - loop start beat 2 -> 2/4 pickup bar."""
        num, den = part.meter
        if den != 4:
            return
        beat = self._tick_in(part, frame) / self.ppq
        b = round(beat) if abs(beat - round(beat)) <= 0.25 else math.floor(beat)
        self.downbeat_tick = max(0, b) * self.ppq
        lead = b % num
        if b < 1 or lead == 0:
            return
        part.lead_beats = lead
        part.bar_origin = part.origin_tick + lead * self.ppq

    def _compound_pickup(self, part, notes, end, downbeat):
        """v0.1.43: a 6/8 tune whose dotted-quarter beats start one or two 8ths after the grid
        origin (part.meter_phase) begins with a pickup. The downbeat is the beat the loop start
        falls on (or just after), else the beat where the long notes weigh more. A pickup that is
        not a whole dotted beat gets rests in front (user rule: pad the pickup to whole beats), so
        the first bar is 3/8 or 6/8.
        Example: Ma Bu Mi Zhen & Qu Wei Cheng t3 - one 8th (D#4) before the first bass drum:
        3/8 (two 8ths rest + the pickup), then 6/8."""
        e = self.ppq / 2
        o = part.meter_phase
        cands = (o, o + 3)
        if downbeat is not None:
            ls = (self._tick_in(part, downbeat) - part.origin_tick) / e
            d = min(cands, key=lambda c: (ls - c) % 6)
        else:
            w = {c: 0.0 for c in cands}
            for lst in (notes or {}).values():
                starts = [n.start for n in lst if part.origin_frame - 1 <= n.start < end]
                for a, b in zip(starts, starts[1:]):
                    q = round((self._tick_in(part, a) - part.origin_tick) / e)
                    if q % 6 in w:
                        w[q % 6] += min(6.0, (self._tick_in(part, b) - self._tick_in(part, a)) / e)
            d = max(cands, key=lambda c: w[c])
        lead = d % 6
        if lead == 0:
            part.bar_origin = part.origin_tick
            return
        pad = (3 - lead % 3) % 3
        part.lead_tick = part.origin_tick
        part.origin_tick += pad * e
        part.bar_origin = part.origin_tick + lead * e
        part.lead_meter = (lead + pad, 8)

    def _phase_downbeat(self, part, notes, end):
        """v0.1.33: a tune without a loop has no loop start to put on a bar line. Long notes and
        bass notes start on the downbeat more than on the other beats, so the beat of the bar
        (0 .. num-1, counted from the start) where they weigh most is taken as the downbeat when it
        clearly beats beat 0 (the first beats then become a pickup bar).
        Weight of a note starting on a beat: its length in beats (up to 4), twice for the bass
        (the channel with the lowest notes).
        Example: Dragon Quest III t26 - a 2-beat pickup (triplet run into a long G); per beat of
        the bar 275 / 102 / 313 / 126 for the long notes and 50 / 39 / 95 / 42 for the bass."""
        num, den = part.meter
        if den != 4 or num < 2:
            return
        r = self.phase_scores(part, notes, end)
        if r is None:
            return
        score, count, per, bass = r
        best = max(range(num), key=lambda p: score[p])
        entry = self._bass_entry(part, per, bass, num)
        if entry is not None and count >= PHASE_MIN_NOTES and score[0] < PHASE_GAIN * score[entry]:
            # v2.9.31: the bass comes in after an intro without it: its entry is a downbeat (user rule:
            # a pickup has no bass). Pooyan t1 - sound effects in P1 for 7 s, then the triangle G#3
            # (2 beats) on beat 18 and every 4 beats; the weights alone were a tie (56 / 59 for beats
            # 0 and 2), now the D3 + A4 at 13.5 s (beat 34) starts a bar
            if entry:
                part.lead_beats = entry
                part.bar_origin = part.origin_tick + entry * self.ppq
            return
        if count < PHASE_MIN_NOTES or best == 0 or score[best] < PHASE_GAIN * score[0]:
            return
        # v0.1.33: the opening must look like a pickup: before beat `best` only short notes (< 1 beat),
        # and the first long note starts right on it (DQ3 t26: G C D as triplets, then a long G).
        # James Bond Jr. t1 has its weight on beat 2 all through but no pickup.
        # v2.9.30: short tunes too (v0.1.33-v2.9.29 skipped tunes under 30 s; user: "undo it".
        # Adventure Island 3 t1, 14 s, now a 2-beat pickup, its shuffle was the problem)
        first_long = None
        for sel in per.values():
            for n in sel:
                t = self._tick_in(part, n.start) - part.origin_tick
                d = (self._tick_in(part, n.gate_end if n.gate_end is not None else n.end)
                     - part.origin_tick - t) / self.ppq
                if d >= 1 and (first_long is None or t < first_long):
                    first_long = t
        if first_long != best * self.ppq:
            return
        part.lead_beats = best
        part.bar_origin = part.origin_tick + best * self.ppq

    def phase_scores(self, part, notes, end):
        """Weight of the notes starting on each beat of the bar (0 .. num-1, counted from the part's
        origin): length in beats (up to 4), twice for the bass (the channel with the lowest notes).
        Returns (score, count, per, bass) or None (see _phase_downbeat)."""
        num = part.meter[0]
        per = {}
        for ch, lst in notes.items():
            sel = [n for n in lst if part.origin_frame - 1 <= n.start < end]
            if len(sel) >= 8:
                per[ch] = sel
        if not per:
            return
        bass = min(per, key=lambda ch: sorted(n.pitch for n in per[ch])[len(per[ch]) // 2])
        score = [0.0] * num
        count = 0
        for ch, sel in per.items():
            for n in sel:
                t = self._tick_in(part, n.start) - part.origin_tick
                if t < 0 or t % self.ppq:
                    continue
                dur = (self._tick_in(part, n.gate_end if n.gate_end is not None else n.end)
                       - part.origin_tick - t) / self.ppq
                if dur <= 0:
                    continue
                score[int(t // self.ppq) % num] += min(4.0, dur) * (2 if ch == bass else 1)
                count += 1
        return score, count, per, bass

    def _bass_entry(self, part, per, bass, num):
        """v2.9.31: the beat of the bar (0 .. num-1) where the bass enters after an intro of at least a
        bar without it, or None. The entry must be a note of a beat or more starting on a beat, and
        other channels must have played before it."""
        first = per[bass][0]
        t = self._tick_in(part, first.start) - part.origin_tick
        others = [lst[0].start for ch, lst in per.items() if ch != bass]
        if not others or t % self.ppq or t < num * self.ppq:
            return None
        if self._tick_in(part, min(others)) - part.origin_tick > t - num * self.ppq:
            return None                 # the others start less than a bar before it
        d = (self._tick_in(part, first.gate_end if first.gate_end is not None else first.end)
             - part.origin_tick - t) / self.ppq
        if d < 1:
            return None
        return int(t // self.ppq) % num

    def _detect_meter(self, part, notes, end):
        """6/8 if notes longer than one 8th start on 3-eighth boundaries, else 4/4."""
        rows = part.seg.rows
        if notes is None or rows % 2:
            return (4, 4)
        eighth = rows // 2
        pos = []
        for lst in notes.values():
            starts = [n.start for n in lst if part.origin_frame - 1 <= n.start < end]
            for a, b in zip(starts, starts[1:] + [None]):
                ra = part.rows_at(a)
                if b is not None and part.rows_at(b) - ra < 2 * eighth - 0.5:
                    continue                # short note
                pos.append(int(round(ra / eighth)))
        if len(pos) < COMPOUND_MIN_NOTES:
            return (4, 4)
        s3 = sum(1 for p in pos if p % 3 == 0) / len(pos)
        s2 = sum(1 for p in pos if p % 2 == 0) / len(pos)
        if s3 >= COMPOUND_FIT and s3 - s2 >= COMPOUND_GAIN:
            return (6, 8)
        # v0.1.43: the same with the beats one or two 8ths later (a pickup 8th: Ma Bu Mi Zhen & Qu
        # Wei Cheng t3, 99 % of the long notes one 8th after the 3-8th boundaries from the start)
        s2 = max(sum(1 for p in pos if (p - o) % 2 == 0) for o in (0, 1)) / len(pos)
        for o in (1, 2):
            s3 = sum(1 for p in pos if (p - o) % 3 == 0) / len(pos)
            if s3 >= COMPOUND_FIT and s3 - s2 >= COMPOUND_GAIN:
                part.meter_phase = o
                return (6, 8)
        if self._repeats_in_six(part, notes, end):
            # v0.1.44: the phase of the loop start (running 8ths: the long notes do not tell the
            # bars; Relics t3 - the loop starts on the F where the bass comes in, the user's
            # downbeat, one 8th after the 3-8th boundaries of the long notes)
            ls = part.rows_at(self.loop[0]) / eighth
            part.meter_phase = int(round(ls)) % 3
            return (6, 8)
        return (4, 4)

    def _repeats_in_six(self, part, notes, end):
        """v0.1.43: 6/8 in running 8ths (no long notes to tell the bars): the melody comes back
        after 6 8ths far more often than after 4 or 8 (Indora no Hikari t1: 0.75 vs 0 / 0,
        Relics t3: 0.25 vs 0.04 / 0.07), and the loop is a whole number of 6/8 bars (Minna no Taabou
        t2 repeats after 6 8ths too, but its loop of 128 8ths is 4/4). Channels sounding the same
        pitch all the time (a pedal) are left out."""
        if not self.loop or part.seg.rows % 2:
            return False
        e = part.seg.rows // 2
        start, period = self.loop
        if not part.origin_frame - 1 <= start < end:
            return False
        n8 = (part.rows_at(start + period) - part.rows_at(start)) / e
        if abs(n8 - round(n8)) > 0.1 or round(n8) % 6 or round(n8) % 8 == 0 and round(n8) % 24:
            return False
        best = None
        for lst in notes.values():
            sel = [n for n in lst if part.origin_frame - 1 <= n.start < end]
            if len(sel) < 40:
                continue
            at = {round(part.rows_at(n.start)): n.pitch for n in sel}
            rep = {}
            for k in (4, 6, 8):
                lag = k * e
                rep[k] = sum(1 for r, p in at.items() if any(at.get(r + lag + x) == p for x in (-1, 0, 1))) / len(at)
            if min(rep.values()) >= 0.9:
                continue                    # a pedal
            if best is None or rep[6] > best[6]:
                best = rep
        return bool(best) and best[6] >= REP6_MIN and best[6] >= REP6_RATIO * max(best[4], best[8])

    # -------------------------------------------------------------- mapping
    def _bar_after(self, prev, frame):
        """Tick of the bar line where a segment starting at `frame` begins."""
        last_tick = self._tick_in(prev, prev.last_onset)
        bar = prev.bar_ticks
        rel = last_tick - prev.bar_origin
        nxt = prev.bar_origin + (int(rel // bar) + 1) * bar
        natural = self._tick_in(prev, frame)
        if frame - prev.last_onset <= CONTINUOUS_ROWS * prev.seg.unit:
            # v0.1.29: the music goes on without a break (a ritardando that became its own
            # segment, Dragon Quest III t15): no bar-line jump, the segment starts where it falls
            return natural
        if natural - nxt > 2 * bar:
            # a real multi-bar rest: keep its length, aligned to the bar grid
            nxt = prev.bar_origin + int(round((natural - prev.bar_origin) / bar)) * bar
        return nxt

    def _tick_in(self, part, frame):
        rows = part.rows_at(frame)
        if self.quantize:
            r = round(rows)
            R = part.seg.rows
            if (R % 3 == 0 and R % 4 and frame in self.onset_set
                    and abs(rows - r) * part.seg.unit >= MIXED_TRIPLET_ERR):
                # v0.1.28: 16ths inside a triplet grid (Wrecking Crew t1: a 16th pickup before
                # the shuffle) go on the 16th of the beat instead of the nearest triplet row
                q = rows * 4 / R
                if abs(q - round(q)) * part.seg.unit * R / 4 <= MIXED_16TH_ERR:
                    return part.origin_tick + round(q) * R / 4 * part.tpu
            rows = r
        return part.origin_tick + rows * part.tpu

    def _part_for(self, frame):
        part = self.parts[0]
        for p in self.parts[1:]:
            if frame >= p.origin_frame - p.seg.unit / 2:
                part = p
        return part

    def __call__(self, frame):
        return max(0, int(round(self._tick_in(self._part_for(frame), frame))))

    @property
    def min_ticks(self):
        return min(p.tpu for p in self.parts)

    def _bpm(self, frames_per_row, part):
        return 60.0 * self.fr / (frames_per_row * part.seg.rows)

    def tempo_events(self):
        ev = []
        for k, p in enumerate(self.parts):
            if k > 0:
                # gap from the previous part's last note to this bar line
                prev = self.parts[k - 1]
                t_last = self._tick_in(prev, prev.last_onset)
                dt = (p.origin_tick - t_last) / self.ppq
                df = p.origin_frame - prev.last_onset
                if dt > 0 and df > 0:
                    ev.append((t_last, 60.0 * self.fr * dt / df))
            if not p.anchors:
                ev.append((p.origin_tick, p.seg.bpm))
                continue
            # one tempo per bar (averages out the +-1 frame jitter of accumulator drivers,
            # follows a ritardando bar by bar)
            rpb = p.bar_ticks / p.tpu
            last_row = p.anchors[-1][1]
            b = 0
            while b * rpb < last_row:
                r0, r1 = b * rpb, min((b + 1) * rpb, last_row)
                if r1 - r0 < 1:
                    break
                fpr = (p.frame_at_row(r1) - p.frame_at_row(r0)) / (r1 - r0)
                ev.append((p.origin_tick + r0 * p.tpu, self._bpm(fpr, p)))
                b += 1
        # drop redundant events (< 1 % change); a later event at the same tick wins
        out = []
        for tick, bpm in sorted(ev, key=lambda e: e[0]):
            tick = max(0, int(round(tick)))
            if out and out[-1][0] == tick:
                out[-1] = (tick, bpm)
                if len(out) > 1 and abs(bpm - out[-2][1]) / out[-2][1] < 0.01:
                    out.pop()
            elif not out or abs(bpm - out[-1][1]) / out[-1][1] >= 0.01:
                out.append((tick, bpm))
        return out

    def meter_events(self):
        ev = []
        for p in self.parts:
            if p.lead_meter:
                ev.append((int(round(p.lead_tick)), p.lead_meter))
            elif p.lead_beats:
                ev.append((int(round(p.origin_tick)), (p.lead_beats, 4)))
            elif p.short_bar:
                ev.append((int(round(p.origin_tick)), p.meter))
                ev.append((int(round(p.short_bar[0])), p.short_bar[1]))
            ev.append((int(round(p.bar_origin)), p.meter))
        if self.extra_meters:
            # odd bars inside the loop (meter.odd_bars, v0.1.30): they replace the meter events
            # in their range; the base meter comes back at the end of the range
            lo, hi, base = self.extra_meters[0][0], self.extra_range_end, self.extra_base
            ev = [e for e in ev if not lo <= e[0] < hi] + list(self.extra_meters)
            if not any(t == hi for t, _ in ev):
                ev.append((hi, base))
            ev.sort(key=lambda e: e[0])
            out = []
            for t, m in ev:
                if out and out[-1][0] == t:
                    out[-1] = (t, m)
                elif not out or out[-1][1] != m:
                    out.append((t, m))
            ev = out
        return ev

    def set_odd_meters(self, events, range_end, base):
        """Time signatures [(tick, meter)] for a stretch (the loop, repeated) ending at range_end."""
        self.extra_meters = sorted(events)
        self.extra_range_end = range_end
        self.extra_base = base
