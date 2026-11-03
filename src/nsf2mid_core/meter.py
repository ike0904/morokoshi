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


def odd_bars(events, start_tick, end_tick):
    """events: [(tick, channel, kind, is_snare)] of all notes and drum hits.
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
