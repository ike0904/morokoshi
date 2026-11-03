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


def _fit(onsets, unit):
    phase = _phase(onsets, unit)
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
    return best_s if best >= SHUFFLE_PAIRS else None


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


def choose_rows(unit, frame_rate, ternary, prefer_bpm=None, onsets=None):
    family = (12, 6, 3, 24) if ternary else (4, 2, 8, 16)
    if prefer_bpm:
        # keep continuity with the previous segment
        return min(family, key=lambda m: abs(math.log((60.0 * frame_rate / (unit * m)) / prefer_bpm)))
    if ternary and onsets and len(onsets) > 8:
        # the most common interval is an 8th note (half a beat), if that gives a sane tempo
        # (Super Mario Bros.: grid 3 frames, mostly 9-frame 8ths -> 6 rows/beat = 200 BPM,
        # triplets are 6 frames = 2 rows)
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
                     tempo="auto"):
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
        ternary = bool(trip_d) or triplets == "on"
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
            s.rows = choose_rows(s.unit, frame_rate, ternary, prev, onsets)
        s.bpm = 60.0 * frame_rate / (s.unit * s.rows)
        prev = s.bpm
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
    return {"tempo_kept": kept, "global": g, "segments": segs, "ternary": ternary, "shuffle": shuffle, "triplet": bool(trip_d)}


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
                and lg["score"] >= LOCAL_MIN and lg["score"] - gfit >= LOCAL_GAIN):
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
            if abs(u - pu) / pu < MERGE_RATIO:
                merged[-1][1].extend(sub)
                continue
        merged.append([lab, list(sub)])
    runs = merged

    segs = []
    for lab, sub in runs:
        u = g["unit"] if lab is None else lab
        if lab is not None:
            lg = detect_grid(sub, max(2.0, u * 0.95), min(48.0, u * 1.05))
            if lg:
                u = lg["unit"]
        ph = _phase(sub, u)
        sc = sum(_hits(sub, u, ph)) / len(sub)
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


def _same(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) / a < 0.015


TRACK_FIT = 0.9          # segments fitting worse than this are tempo-tracked (rubato / ritardando)
RIT_MIN = 1.045          # v0.1.29: a run of notes this much longer than the channel's usual note ...
RIT_MAX = 1.6            # ... (but not as long as a different note value) ...
RIT_RUN = 3              # ... for this many notes in a row is a ritardando
CONTINUOUS_ROWS = 2      # v0.1.29: a segment starting this close after the last note keeps its natural tick


JITTER_TOL = 1.5        # v0.1.31: frames; onsets this close to the grid ...
JITTER_FIT = 0.9        # ... this often = a steady tempo whose notes are rounded to frames


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


def has_ritardando(starts, unit):
    """A ritardando inside a segment that still fits its grid: the notes of one channel get
    gradually longer than its usual note (e.g. 19 frames per 8th -> 21, 24, 26, 28, 26, 24, 21),
    so the slow notes round up to extra rows and the bars drift. Runs of one longer value
    (dotted notes: 28, 28, 28) do not count - the lengths must change along the run, step by
    step (no jump of more than 0.2 x the usual note), and grow from the first note of the run
    (a run that only gets shorter is a speed-up into the tempo, e.g. the Airball intro).

    Example: Dragon Quest III t15 - 8ths of 19 frames slow down twice in the loop."""
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
    run = []
    for i in iois + [0]:
        r = i / d
        if RIT_MIN < r < RIT_MAX:
            run.append(r)
            continue
        if (len(run) >= RIT_RUN and max(run) - min(run) >= 0.05 and any(abs(x - 1.5) > 0.07 for x in run)
                and max(run) >= run[0] + 0.05 and all(abs(b - a) <= 0.2 for a, b in zip(run, run[1:]))):
            return True
        run = []
    return False
COMPOUND_MIN_NOTES = 3
COMPOUND_FIT = 0.85      # long notes on 3-eighth boundaries (dotted-quarter beats) ...
COMPOUND_GAIN = 0.15     # ... clearly more often than on 2-eighth boundaries
BEAT_PHASE_GAIN = 1.15   # ternary grid: another row starts the beat if it scores this much better (v0.1.28)
MIXED_TRIPLET_ERR = 1.5  # ternary grid: an onset this many frames off the triplet rows ...
MIXED_16TH_ERR = 0.5     # ... and this close to a 16th of the beat is placed on the 16th (v0.1.28)


def beat_phase(onsets, unit, origin, rows):
    """Ternary grids (3 / 6 rows per beat): which row (mod rows) starts the beat. Each onset
    scores the rows until the next onset (capped at one beat): in a shuffle the long note of
    the long-short pair starts on the beat, and longer notes start on beats in general.
    Returns the row offset p (0 = the grid point near frame 0 is a beat), a multiple of rows / 3.

    Example: Wrecking Crew t1 - grid 8 frames from frame -4, 16+8 shuffle from frame 108
    (row 14): the beats are rows 2, 5, 8, ... (p = 2)."""
    score = [0.0] * rows
    pos = [round((o - origin) / unit) for o in onsets]
    for a, b in zip(pos, pos[1:] + [None]):
        w = rows if b is None else min(rows, b - a)
        if w > 0:
            score[a % rows] += w
    # only shifts by whole triplet 8ths (a shift by half a beat is a binary question, not handled)
    best = max(range(0, rows, rows // 3), key=lambda p: score[p])
    return best if score[best] >= BEAT_PHASE_GAIN * score[0] and score[best] > score[0] else 0


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
                 meters=None, downbeat=None):
        self.ppq = ppq
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
                    p = beat_phase(seg_on, s.unit, origin, s.rows)
                    if p:
                        origin -= (s.rows - p) * s.unit
            else:
                origin = s.start
                origin_tick = self._bar_after(self.parts[-1], origin)
            anchors, unit_end = [], s.unit
            rit = s.score >= TRACK_FIT and notes is not None and any(
                has_ritardando([n.start for n in lst if (k == 0 or n.start >= s.start) and n.start < end], s.unit)
                for lst in notes.values())
            s.rit = rit
            jitter = s.score < TRACK_FIT and not rit and steady_with_jitter(seg_on, s.unit, s.phase)
            if (s.score < TRACK_FIT and not jitter or rit) and len(seg_on) >= 4:
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
            if k == 0 and downbeat is not None and (len(segs) == 1 or downbeat < segs[1].start):
                self._set_downbeat(part, downbeat)
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
        return (4, 4)

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
            if p.lead_beats:
                ev.append((int(round(p.origin_tick)), (p.lead_beats, 4)))
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
