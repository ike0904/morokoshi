"""
Odd bars inside a loop (v0.1.30).

When the loop is not a whole number of 4/4 bars, the tune has bars of another length somewhere
(Life Force t3: 4/4 x8, then the loop 6/8 6/8 5/8 6/8 6/8 5/8 and 4/4 x11 = 61 beats).
The loop start and the loop end are bar lines (TickMap puts the loop start on a downbeat), so:

  - the 4/4 bars before the odd part keep the phase of the loop start, the 4/4 bars after it
    keep the phase of the loop end; the odd part is one stretch between them
  - inside the odd part, a bar of L eighths is good when the same rhythm comes again right
    before or after it (local repetition: the 6/8 bars repeat, the 5/8 fills do not); each bar
    that is not 4/4 costs a penalty
  - a drum fill (snare on the 3 eighths before) ends on a bar line, in every part

A dynamic programme over the eighths of the loop finds the cheapest bars. Channels that start a
note on (almost) every eighth (a bass ostinato) carry no rhythm and are left out.

v0.1.32: phrase first (the user's idea: find the blocks of bars). The odd bars usually come as a
phrase played twice in a row (Dragon Quest IV t13: 45 eighths, the second time an octave up;
Life Force t3: 17; Shatterhand t1: 34 = 6/8 x3 + 4/4 x2). The best such repeat that is not a
whole number of 4/4 bars (compared by pitch class, so octave transpositions match) fixes the odd
stretch; only the phrase is then cut into bars, the same way both times:
  - a bar is good when the next / previous bar (or the one after that: 9/8 bars 1 and 3 of Dragon
    Quest IV are the same notes) repeats it - half by rhythm (all channels, without the ones
    sounding on every eighth), half by the notes of the best single channel (a bass ostinato
    repeating exactly marks the 7/8 bars); the better of the two rounds of the phrase counts
  - a penalty for each bar that is not 4/4, smaller for longer bars
If no phrase repeats well enough, the v0.1.30 method is used.
"""

from functools import lru_cache

EIGHTH = 240                    # ticks (PPQ 480)
BAR = 8                         # eighths in the base 4/4 bar
LENGTHS = (8, 6, 5, 7, 9, 4, 3, 2)
ODD_PEN = 0.5                   # cost of a bar that is not 4/4
ODD_PEN_SHORT = 0.75            # ... of a bar of 2 or 3 eighths
ODD_PEN_LONG = 0.8              # ... of a 9/8 bar (v0.1.31; a 3-eighth rhythm stays 6/8, Shatterhand)
FILL_BONUS = 0.5                # a bar line right after a drum fill
DENSE = 0.9                     # channels with notes on this share of the eighths are ignored
SNARES = {37, 38, 39, 40}


def _meter(L, pattern):
    """Time signature of a bar of L eighths. 6 eighths: 6/8 when the two halves of the bar
    have the same rhythm (3 + 3), 3/4 when the three quarters are more alike (2 + 2 + 2)."""
    if L == 6:
        def part(lo, hi):
            return {(i - lo,) + tuple(k[:2]) for i, *k in pattern if lo <= i < hi}

        def alike(a, b):
            return len(a & b) / max(len(a | b), 1)
        halves = alike(part(0, 3), part(3, 6))
        thirds = (alike(part(0, 2), part(2, 4)) + alike(part(2, 4), part(4, 6))) / 2
        return (6, 8) if halves >= thirds else (3, 4)
    if L % 2 == 0:
        return (L // 2, 4)
    return (L, 8)


def _region_bars(events, start_tick, end_tick):
    """v0.1.30 method: one stretch of odd bars between 4/4 locked to the loop ends.
    events: [(tick, channel, kind, is_snare)] of all notes and drum hits.
    Returns [(tick, (num, den))] time signatures for the loop [start_tick, end_tick), or None
    when the loop is a whole number of 4/4 bars or not a whole number of eighths."""
    span = end_tick - start_tick
    n = int(round(span / EIGHTH))
    if n <= 0 or abs(span - n * EIGHTH) > EIGHTH / 8 or n % BAR == 0:
        return None
    ev = {}
    snare, snare_on = set(), set()      # eighths with a snare hit / with one right on the eighth
    for tick, ch, kind, is_snare in events:
        if not start_tick - 3 * EIGHTH <= tick < end_tick + BAR * EIGHTH:
            continue
        e, off = divmod(tick - start_tick, EIGHTH)
        ev.setdefault(e, set()).add((ch, off, kind))
        if is_snare:
            snare.add(e)
            if off == 0:
                snare_on.add(e)
    count = {}
    for e in range(n):
        for ch in {k[0] for k in ev.get(e, ())}:
            count[ch] = count.get(ch, 0) + 1
    dense = {ch for ch, c in count.items() if c >= DENSE * n and not ch.startswith("DRUM")}
    ev = {e: {k for k in s if k[0] not in dense} for e, s in ev.items()}

    def pattern(a, L):
        return {(i,) + k for i in range(L) for k in ev.get(a + i, ())}

    @lru_cache(None)
    def rep(a, L):
        p = pattern(a, L)
        best = 0.0
        for b in (a - L, a + L):
            q = pattern(b, L)
            if p or q:
                best = max(best, len(p & q) / max(len(p), len(q)))
        return max(0.0, 2 * best - 1)       # half the notes in common is no repetition

    def fill_end(a):
        return all(e in snare for e in (a - 1, a - 2, a - 3)) and a not in snare_on

    # states: 0 = 4/4 from the loop start, 1 = odd part, 2 = 4/4 up to the loop end
    best = {(0, 0): (0.0, None)}
    for a in range(n):
        bonus = FILL_BONUS if fill_end(a) else 0.0
        for st in (0, 1, 2):
            if (a, st) not in best:
                continue
            c0 = best[(a, st)][0]
            for L in LENGTHS:
                b = a + L
                if b > n:
                    continue
                for nst in ((0, 1) if st == 0 else (1, 2) if st == 1 else (2,)):
                    if nst != 1 and L != BAR:
                        continue
                    if nst == 1:
                        pen = 0.0 if L == BAR else ODD_PEN_SHORT if L <= 3 else ODD_PEN_LONG if L > BAR else ODD_PEN
                        c = c0 + pen - rep(a, L) * L / BAR - bonus
                    else:
                        c = c0 - bonus
                    if (b, nst) not in best or c < best[(b, nst)][0] - 1e-9:
                        best[(b, nst)] = (c, (a, st, L))
    ends = [k for k in best if k[0] == n]
    if not ends:
        return None
    k = min(ends, key=lambda x: best[x][0])
    bars = []
    while best[k][1]:
        a, st, L = best[k][1]
        bars.append((a, L))
        k = (a, st)
    bars.reverse()
    out, prev = [], None
    for a, L in bars:
        m = _meter(L, pattern(a, L))
        if m != prev:
            out.append((start_tick + a * EIGHTH, m))
            prev = m
    return out


# ---------------------------------------------------------------- v0.1.32: phrase first
PHRASE_MIN = 9          # eighths
PHRASE_SIM = 0.8        # share of the notes (pitch class) the two rounds have in common
PH_PEN = 0.25           # penalty of an odd bar (5, 6, 7 eighths) inside the phrase
PH_PEN_4 = 0.4          # ... of a 2/4 bar
PH_PEN_LONG = 0.3       # ... of a 9/8 bar
PH_PEN_SHORT = 0.75     # ... of a bar of 2 or 3 eighths
PH_PEN_TRIPLE = 0.5     # extra for a 9/8 bar made of three equal groups of 3 eighths (that is 6/8)


def _events(events, start_tick, n, pitch):
    """{eighth: {(channel, offset, key)}}; key of a tonal note: "exact" pitch, pitch "class" or
    none (rhythm only); drums always keep their kind."""
    ev = {}
    for tick, ch, kind, _ in events:
        e, off = divmod(tick - start_tick, EIGHTH)
        if -BAR * 3 <= e < n + BAR * 3:
            if ch.startswith("DRUM") or pitch == "exact":
                k = kind
            else:
                k = kind % 12 if pitch == "class" else ""
            ev.setdefault(e, set()).add((ch, off, k))
    return ev


def _pat(ev, a, L, ch=None):
    return {(i,) + k for i in range(L) for k in ev.get(a + i, ()) if ch is None or k[0] == ch}


def _jac(p, q):
    return len(p & q) / max(len(p), len(q)) if (p or q) else 0.0


def find_phrase(events, start_tick, n):
    """(start, length) in eighths of the best phrase played twice in a row whose two rounds are
    not whole 4/4 bars and leave whole 4/4 bars around them, or None."""
    ev = _events(events, start_tick, n, "class")
    best = None
    for s0 in range(0, n, BAR):
        for Lp in range(PHRASE_MIN, (n - s0) // 2 + 1):
            if (2 * Lp) % BAR != n % BAR or (n - s0 - 2 * Lp) % BAR:
                continue
            sim = _jac(_pat(ev, s0, Lp), _pat(ev, s0 + Lp, Lp))
            if sim >= PHRASE_SIM and (best is None or sim > best[0]):
                best = (sim, s0, Lp)
    return best and best[1:]


def split_phrase(events, start_tick, n, s0, Lp, snare, snare_on):
    """Bar lengths (eighths) that cut the phrase [s0, s0 + Lp) (played again right after)."""
    rhythm = _events(events, start_tick, n, "none")
    notes = _events(events, start_tick, n, "exact")
    chans = sorted({k[0] for s_ in notes.values() for k in s_})

    @lru_cache(None)
    def rep_rhythm(a, L):
        best = 0.0
        for b in (a - L, a + L):
            P, Q = set(), set()
            for ch in chans:
                p, q = _pat(rhythm, a, L, ch), _pat(rhythm, b, L, ch)
                if not ch.startswith("DRUM") and \
                        len({x[0] for x in p}) + len({x[0] for x in q}) >= DENSE * 2 * L:
                    continue                    # sounds on every eighth: no rhythm information
                P |= p
                Q |= q
            best = max(best, _jac(P, Q))
        return max(0.0, 2 * best - 1)

    @lru_cache(None)
    def rep_notes(a, L):
        best = 0.0
        for k in (-2, -1, 1, 2):
            for ch in chans:
                p, q = _pat(notes, a, L, ch), _pat(notes, a + k * L, L, ch)
                if len(p) >= 3 and len(q) >= 3:
                    best = max(best, _jac(p, q))
        return max(0.0, 2 * best - 1)

    def fill_end(a):
        return all(e in snare for e in (a - 1, a - 2, a - 3)) and a not in snare_on

    def three_groups(a):
        """The 3-eighth groups of a 9/8 bar are all alike (Shatterhand: a 3-eighth figure that
        6/8 bars explain as well; real 9/8 bars of Dragon Quest IV run 2 + 2 + 2 + 3)."""
        g = [_pat(rhythm, a + 3 * i, 3) for i in range(3)]
        return all(_jac(g[0], g[i]) >= 0.9 for i in (1, 2)) and len(g[0]) > 0

    def cost(a, L):
        if L == BAR:
            pen = 0.0
        elif L <= 3:
            pen = PH_PEN_SHORT
        elif L == 4:
            pen = PH_PEN_4
        elif L > BAR:
            pen = PH_PEN_LONG
        else:
            pen = PH_PEN
        if L == 9 and any(three_groups(c + a) for c in (s0, s0 + Lp)):
            pen += PH_PEN_TRIPLE
        r = max(0.5 * rep_rhythm(c + a, L) + 0.5 * rep_notes(c + a, L) for c in (s0, s0 + Lp))
        bonus = sum(FILL_BONUS for c in (s0, s0 + Lp) if fill_end(c + a)) / 2
        return pen - r * L / BAR - bonus

    best = {0: (0.0, None)}
    for a in range(Lp):
        if a not in best:
            continue
        for L in LENGTHS:
            if a + L <= Lp:
                c = best[a][0] + cost(a, L)
                if a + L not in best or c < best[a + L][0] - 1e-9:
                    best[a + L] = (c, (a, L))
    bars, b = [], Lp
    while best[b][1]:
        a, L = best[b][1]
        bars.append(L)
        b = a
    return bars[::-1]


def odd_bars(events, start_tick, end_tick):
    """events: [(tick, channel, kind, is_snare)]; kind = MIDI note of a tonal note, drum kind of
    a drum hit. Returns [(tick, (num, den))] time signatures for the loop [start_tick, end_tick),
    or None when the loop is a whole number of 4/4 bars or not a whole number of eighths."""
    span = end_tick - start_tick
    n = int(round(span / EIGHTH))
    if n <= 0 or abs(span - n * EIGHTH) > EIGHTH / 8 or n % BAR == 0:
        return None
    ph = find_phrase(events, start_tick, n)
    if not ph:
        return _region_bars([(t, ch, k if ch.startswith("DRUM") else "", sn) for t, ch, k, sn in events],
                            start_tick, end_tick)
    s0, Lp = ph
    snare, snare_on = set(), set()
    for tick, ch, kind, is_snare in events:
        if is_snare:
            e, off = divmod(tick - start_tick, EIGHTH)
            snare.add(e)
            if off == 0:
                snare_on.add(e)
    inner = split_phrase(events, start_tick, n, s0, Lp, snare, snare_on)
    rhythm = _events(events, start_tick, n, "none")
    bars = [BAR] * (s0 // BAR) + inner + inner + [BAR] * ((n - s0 - 2 * Lp) // BAR)
    # one time signature per run of bars of the same length (majority: 6/8 or 3/4), so that a
    # bar of rests does not switch it
    starts, a = [], 0
    for L in bars:
        starts.append(a)
        a += L
    meters = [_meter(L, _pat(rhythm, a, L)) for a, L in zip(starts, bars)]
    i = 0
    while i < len(bars):
        j = i
        while j < len(bars) and bars[j] == bars[i]:
            j += 1
        ms = [m for a, m in zip(starts[i:j], meters[i:j]) if _pat(rhythm, a, bars[i])] or meters[i:j]
        top = max(set(ms), key=ms.count)
        meters[i:j] = [top] * (j - i)
        i = j
    out, prev = [], None
    for a, m in zip(starts, meters):
        if m != prev:
            out.append((start_tick + a * EIGHTH, m))
            prev = m
    return out


# ---------------------------------------------------------------- v0.1.41: loops of whole 4/4 bars
RUN_MIN = 3             # odd bars in a row; an excursion that is back in 4/4 within 2 bars stays 4/4 (user)
RUN_ENTER = 1.0         # penalty of an odd stretch (leaving 4/4)
RUN_PEN = 0.1           # penalty of each odd bar (5, 6, 7, 9 eighths)
RUN_PEN_SHORT = 0.4     # ... of a bar of 2, 3 or 4 eighths
RUN_SWITCH = 0.3        # penalty of a change of the bar length inside the odd stretch


def _wrapped(events, start_tick, span):
    """The loop's events, repeated one loop before and after (the loop is played round)."""
    out = []
    for tick, ch, kind, sn in events:
        if start_tick <= tick < start_tick + span:
            for k in (-1, 0, 1):
                out.append((tick + k * span, ch, kind, sn))
    return out


def _rep_funcs(events, start_tick, n):
    """rep(a, L) in 0..1: how well the bar of L eighths at a is repeated by the bar(s) next to it
    (half rhythm without the channels sounding on every eighth, half the notes of one channel)."""
    rhythm = _events(events, start_tick, n, "none")
    notes = _events(events, start_tick, n, "exact")
    chans = sorted({k[0] for s_ in notes.values() for k in s_})

    @lru_cache(None)
    def rep_rhythm(a, L):
        best = 0.0
        for b in (a - L, a + L):
            P, Q = set(), set()
            for ch in chans:
                p, q = _pat(rhythm, a, L, ch), _pat(rhythm, b, L, ch)
                if not ch.startswith("DRUM") and \
                        len({x[0] for x in p}) + len({x[0] for x in q}) >= DENSE * 2 * L:
                    continue
                P |= p
                Q |= q
            best = max(best, _jac(P, Q))
        return max(0.0, 2 * best - 1)

    @lru_cache(None)
    def rep_notes(a, L):
        best = 0.0
        for k in (-2, -1, 1, 2):
            for ch in chans:
                p, q = _pat(notes, a, L, ch), _pat(notes, a + k * L, L, ch)
                if len(p) >= 3 and len(q) >= 3:
                    best = max(best, _jac(p, q))
        return max(0.0, 2 * best - 1)

    def rep(a, L):
        return 0.5 * rep_rhythm(a, L) + 0.5 * rep_notes(a, L)
    return rep, rhythm


def _cycle_breaks(events, start_tick, a, b):
    """{channel: (held, breaks)} for the 8ths a..b-1: a figure of 3 8ths repeating (an arpeggio
    in 8ths) holds while each note is the one 3 8ths before; a break is the first note that is
    not (the figure starts again / the chord changes). Only notes on the 8ths count."""
    at = {}
    for tick, ch, kind, _ in events:
        if not ch.startswith("DRUM") and (tick - start_tick) % EIGHTH == 0:
            at.setdefault(ch, {})[(tick - start_tick) // EIGHTH] = kind
    out = {}
    for ch, m in at.items():
        held, brk = 0, []
        for p in range(a, b):
            if all(m.get(p - i) is not None and m.get(p - i) == m.get(p - i - 3) for i in (1, 2, 3)):
                held += 1
                if m.get(p) != m.get(p - 3):
                    brk.append(p - a)
        out[ch] = (held, brk)
    return out


def _drop_cycle_runs(events, start_tick, bars):
    """v0.1.44: a run of 6/8 (9/8, 3/4) bars on an arpeggio of 3 8ths is 4/4 when the figure starts
    again on the 4/4 bar lines and never on its own bar lines (user: Minna no Taabou t2 is
    3+3+3+3+4 = 16 8ths - the last 4 shows the 4/4). The run must keep the 4/4 bar lines (it
    starts on one and is a whole number of 4/4 bars), else it stays."""
    out, a, i = [], 0, 0
    while i < len(bars):
        L = bars[i]
        j = i
        while j < len(bars) and bars[j] == L:
            j += 1
        span = L * (j - i)
        if L != BAR and L % 3 == 0 and a % BAR == 0 and span % BAR == 0:
            cyc = _cycle_breaks(events, start_tick, a, a + span)
            ch = max(cyc, key=lambda c: cyc[c][0]) if cyc else None
            if ch is not None and cyc[ch][0] >= span // 2:
                brk = cyc[ch][1]
                if len(brk) >= 2 and all(p % BAR == 0 and p % L for p in brk):
                    out += [BAR] * (span // BAR)
                    a += span
                    i = j
                    continue
        out += bars[i:j]
        a += span
        i = j
    return out


def odd_runs(events, start_tick, end_tick):
    """v0.1.41: odd bars in a loop that is a whole number of 4/4 bars (Ys t8: 4/4 x8, 6/8 x8,
    4/4, 9/8 x8, 3/4 x8, 4/4 x2 = 64 beats). The loop is cut into bars so that each bar is
    repeated by its neighbours as well as possible (the same measure as split_phrase); bars that
    are not 4/4 cost a penalty and must come at least RUN_MIN in a row.
    Returns [(tick, (num, den))] or None when the loop stays 4/4."""
    span = end_tick - start_tick
    n = int(round(span / EIGHTH))
    if n <= 0 or abs(span - n * EIGHTH) > EIGHTH / 8 or n % BAR:
        return None
    ev = _wrapped(events, start_tick, span)
    rep, rhythm = _rep_funcs(ev, start_tick, n)

    def pen(L):
        return 0.0 if L == BAR else RUN_PEN_SHORT if L <= 4 else RUN_PEN

    # state: (eighth, run, last): run = odd bars in a row (capped at RUN_MIN), last = length of the
    # last odd bar; last = -1: one 4/4 bar right after an odd stretch (Ys t8: 6/8 x8, one 4/4 bar,
    # 9/8 - going on in odd bars then costs only a switch)
    best = {(0, 0, 0): (0.0, None)}
    for a in range(n):
        for k in [s for s in best if s[0] == a]:
            c0 = best[k][0]
            _, run, last = k
            for L in LENGTHS:
                b = a + L
                if b > n:
                    continue
                if L == BAR:
                    if 0 < run < RUN_MIN:
                        continue
                    nk = (b, 0, -1 if run else 0)
                    c = c0 - rep(a, L)
                else:
                    enter = RUN_SWITCH if last == -1 else RUN_ENTER if run == 0 else 0.0
                    nk = (b, min(run + 1, RUN_MIN), L)
                    c = c0 + pen(L) + enter + (RUN_SWITCH if last > 0 and last != L else 0.0)                         - rep(a, L) * L / BAR
                if nk not in best or c < best[nk][0] - 1e-9:
                    best[nk] = (c, (k, L))
    ends = [k for k in best if k[0] == n and k[1] in (0, RUN_MIN)]
    if not ends:
        return None
    k = min(ends, key=lambda x: best[x][0])
    bars = []
    while best[k][1]:
        k, L = best[k][1]
        bars.append(L)
    bars.reverse()
    bars = _drop_cycle_runs(ev, start_tick, bars)
    if all(L == BAR for L in bars):
        return None
    # one time signature per run of bars of the same length (majority: 6/8 or 3/4), so that a
    # bar of rests does not switch it
    starts, a = [], 0
    for L in bars:
        starts.append(a)
        a += L
    meters = [_meter(L, _pat(rhythm, a, L)) for a, L in zip(starts, bars)]
    i = 0
    while i < len(bars):
        j = i
        while j < len(bars) and bars[j] == bars[i]:
            j += 1
        ms = [m for a, m in zip(starts[i:j], meters[i:j]) if _pat(rhythm, a, bars[i])] or meters[i:j]
        top = max(set(ms), key=ms.count)
        meters[i:j] = [top] * (j - i)
        i = j
    out, prev = [], None
    for a, m in zip(starts, meters):
        if m != prev:
            out.append((start_tick + a * EIGHTH, m))
            prev = m
    return out
