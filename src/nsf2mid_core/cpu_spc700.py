"""
SPC700 CPU core (the sound CPU of the Super Famicom / SNES) for SPC files (v0.1.36, phase 1).

Memory access goes through a bus object with read(addr) / write(addr, value); the I/O
registers ($F0-$FF: timers, DSP address / data, ports) live in the bus. Cycles are counted
in CPU cycles (1.024 MHz). SLEEP / STOP set `halted`. Every opcode is generated as one small
function (like cpu_sm83.py), so the regular instruction groups stay short.
"""

N, V, P, B, H, I, Z, C = 0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01


class CPUSPC700:
    def __init__(self, bus):
        self.bus = bus
        self.a = self.x = self.y = 0
        self.sp = 0xEF
        self.psw = 0
        self.pc = 0
        self.cycles = 0
        self.halted = False
        self.ops = [None] * 256
        self._build()

    # ------------------------------------------------------------------ helpers
    def rd(self, a):
        return self.bus.read(a & 0xFFFF)

    def wr(self, a, v):
        self.bus.write(a & 0xFFFF, v & 0xFF)

    def imm(self):
        v = self.bus.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def imm16(self):
        lo = self.bus.read(self.pc)
        hi = self.bus.read((self.pc + 1) & 0xFFFF)
        self.pc = (self.pc + 2) & 0xFFFF
        return lo | (hi << 8)

    def dp(self, d):
        return (0x100 if self.psw & P else 0) | (d & 0xFF)

    def rd16dp(self, d):
        base = 0x100 if self.psw & P else 0
        return self.bus.read(base | (d & 0xFF)) | (self.bus.read(base | ((d + 1) & 0xFF)) << 8)

    def push(self, v):
        self.bus.write(0x100 | self.sp, v & 0xFF)
        self.sp = (self.sp - 1) & 0xFF

    def pop(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.bus.read(0x100 | self.sp)

    def nz(self, v):
        self.psw = (self.psw & ~(N | Z)) | (v & N) | (0 if v else Z)
        return v

    def branch(self, cond):
        r = self.imm()
        if cond:
            self.pc = (self.pc + (r - 256 if r > 127 else r)) & 0xFFFF
            self.cycles += 2

    # ALU
    def adc(self, a, b):
        c = self.psw & C
        r = a + b + c
        p = self.psw & ~(N | V | H | Z | C)
        if r > 0xFF:
            p |= C
        if (~(a ^ b) & (a ^ r)) & 0x80:
            p |= V
        if ((a & 0xF) + (b & 0xF) + c) > 0xF:
            p |= H
        r &= 0xFF
        self.psw = p | (r & N) | (0 if r else Z)
        return r

    def sbc(self, a, b):
        return self.adc(a, b ^ 0xFF)

    def cmp(self, a, b):
        r = a - b
        self.psw = (self.psw & ~(N | Z | C)) | (C if r >= 0 else 0) | (r & N) | (0 if (r & 0xFF) else Z)

    def asl(self, v):
        self.psw = (self.psw & ~C) | (C if v & 0x80 else 0)
        return self.nz((v << 1) & 0xFF)

    def rol(self, v):
        c = self.psw & C
        self.psw = (self.psw & ~C) | (C if v & 0x80 else 0)
        return self.nz(((v << 1) | c) & 0xFF)

    def lsr(self, v):
        self.psw = (self.psw & ~C) | (v & 1)
        return self.nz(v >> 1)

    def ror(self, v):
        c = self.psw & C
        self.psw = (self.psw & ~C) | (v & 1)
        return self.nz((v >> 1) | (0x80 if c else 0))

    def step(self):
        op = self.bus.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        self.ops[op]()

    # ------------------------------------------------------------ table builder
    def _build(self):
        src, ops = [], {}

        def add(op, body, cyc):
            name = f"op_{op:02x}"
            lines = "\n".join("    " + ln for ln in body.strip("\n").split("\n"))
            src.append(f"def {name}(self):\n{lines}\n    self.cycles += {cyc}\n")
            ops[op] = name

        # addressing modes for the ALU group (low nibble 4..8 of rows 0..B): (setup, operand, cycles)
        modes = {
            4: ("_ad = self.dp(self.imm())", "self.rd(_ad)", 3),                               # d
            0x14: ("_ad = self.dp(self.imm() + self.x)", "self.rd(_ad)", 4),                 # d+X
            5: ("_ad = self.imm16()", "self.rd(_ad)", 4),                                       # !a
            0x15: ("_ad = (self.imm16() + self.x) & 0xFFFF", "self.rd(_ad)", 5),             # !a+X
            6: ("_ad = self.dp(self.x)", "self.rd(_ad)", 3),                                    # (X)
            0x16: ("_ad = (self.imm16() + self.y) & 0xFFFF", "self.rd(_ad)", 5),             # !a+Y
            7: ("_ad = self.rd16dp(self.imm() + self.x)", "self.rd(_ad)", 6),                # [d+X]
            0x17: ("_ad = (self.rd16dp(self.imm()) + self.y) & 0xFFFF", "self.rd(_ad)", 6),  # [d]+Y
            8: ("", "self.imm()", 2),                                                           # #i
        }
        alu = {0: "self.a = self.nz(self.a | _v)", 2: "self.a = self.nz(self.a & _v)",
               4: "self.a = self.nz(self.a ^ _v)", 6: "self.cmp(self.a, _v)",
               8: "self.a = self.adc(self.a, _v)", 0xA: "self.a = self.sbc(self.a, _v)"}
        for row, body in alu.items():
            for low in (4, 5, 6, 7, 8):
                for odd in (0, 1):
                    if low == 8 and odd:
                        continue
                    op = ((row + odd) << 4) | low
                    setup, operand, cyc = modes[low + (0x10 if odd else 0)]
                    add(op, f"{setup}\n_v = {operand}\n{body}", cyc)
        # memory-to-memory ALU: x9 dd,ds / x9 (X),(Y) / x8 d,#i
        mem_alu = {0: "_r = _t | _s", 2: "_r = _t & _s", 4: "_r = _t ^ _s", 6: None,
                   8: "_r = self.adc(_t, _s)", 0xA: "_r = self.sbc(_t, _s)"}
        for row, body in mem_alu.items():
            hi = row << 4
            if body is None:      # CMP: no store
                fin = "self.cmp(_t, _s)"
            elif row in (0, 2, 4):
                fin = body + "\nself.nz(_r)\nself.wr(_ad, _r)"
            else:
                fin = body + "\nself.wr(_ad, _r)"
            add(hi | 0x09, f"_s = self.rd(self.dp(self.imm()))\n_ad = self.dp(self.imm())\n_t = self.rd(_ad)\n{fin}", 6)
            add(hi | 0x19, f"_s = self.rd(self.dp(self.y))\n_ad = self.dp(self.x)\n_t = self.rd(_ad)\n{fin}", 5)
            add(hi | 0x18, f"_s = self.imm()\n_ad = self.dp(self.imm())\n_t = self.rd(_ad)\n{fin}", 5)

        # row C/D/E/F of nibbles 4..7: MOV
        add(0xC4, "self.wr(self.dp(self.imm()), self.a)", 4)
        add(0xD4, "self.wr(self.dp(self.imm() + self.x), self.a)", 5)
        add(0xC5, "self.wr(self.imm16(), self.a)", 5)
        add(0xD5, "self.wr(self.imm16() + self.x, self.a)", 6)
        add(0xC6, "self.wr(self.dp(self.x), self.a)", 4)
        add(0xD6, "self.wr(self.imm16() + self.y, self.a)", 6)
        add(0xC7, "self.wr(self.rd16dp(self.imm() + self.x), self.a)", 7)
        add(0xD7, "self.wr(self.rd16dp(self.imm()) + self.y, self.a)", 7)
        for low in (4, 5, 6, 7):
            for odd in (0, 1):
                setup, operand, cyc = modes[low + (0x10 if odd else 0)]
                add(((0xE + odd) << 4) | low, f"{setup}\nself.a = self.nz({operand})", cyc)
        add(0xE8, "self.a = self.nz(self.imm())", 2)
        add(0xC8, "self.cmp(self.x, self.imm())", 2)
        add(0xD8, "self.wr(self.dp(self.imm()), self.x)", 4)
        add(0xF8, "self.x = self.nz(self.rd(self.dp(self.imm())))", 3)
        add(0xC9, "self.wr(self.imm16(), self.x)", 5)
        add(0xD9, "self.wr(self.dp(self.imm() + self.y), self.x)", 5)
        add(0xE9, "self.x = self.nz(self.rd(self.imm16()))", 4)
        add(0xF9, "self.x = self.nz(self.rd(self.dp(self.imm() + self.y)))", 4)
        add(0xCB, "self.wr(self.dp(self.imm()), self.y)", 4)
        add(0xDB, "self.wr(self.dp(self.imm() + self.x), self.y)", 5)
        add(0xEB, "self.y = self.nz(self.rd(self.dp(self.imm())))", 3)
        add(0xFB, "self.y = self.nz(self.rd(self.dp(self.imm() + self.x)))", 4)
        add(0xCC, "self.wr(self.imm16(), self.y)", 5)
        add(0xEC, "self.y = self.nz(self.rd(self.imm16()))", 4)
        add(0x8D, "self.y = self.nz(self.imm())", 2)
        add(0xCD, "self.x = self.nz(self.imm())", 2)
        add(0xAD, "self.cmp(self.y, self.imm())", 2)
        add(0x1E, "self.cmp(self.x, self.rd(self.imm16()))", 4)
        add(0x3E, "self.cmp(self.x, self.rd(self.dp(self.imm())))", 3)
        add(0x5E, "self.cmp(self.y, self.rd(self.imm16()))", 4)
        add(0x7E, "self.cmp(self.y, self.rd(self.dp(self.imm())))", 3)
        add(0x8F, "_v = self.imm()\nself.wr(self.dp(self.imm()), _v)", 5)
        add(0xFA, "_v = self.rd(self.dp(self.imm()))\nself.wr(self.dp(self.imm()), _v)", 5)
        add(0xAF, "self.wr(self.dp(self.x), self.a)\nself.x = (self.x + 1) & 0xFF", 4)
        add(0xBF, "self.a = self.nz(self.rd(self.dp(self.x)))\nself.x = (self.x + 1) & 0xFF", 4)
        # register moves
        add(0x5D, "self.x = self.nz(self.a)", 2)
        add(0x7D, "self.a = self.nz(self.x)", 2)
        add(0xDD, "self.a = self.nz(self.y)", 2)
        add(0xFD, "self.y = self.nz(self.a)", 2)
        add(0x9D, "self.x = self.nz(self.sp)", 2)
        add(0xBD, "self.sp = self.x", 2)
        # shifts / inc / dec
        for row, fn in ((0, "asl"), (2, "rol"), (4, "lsr"), (6, "ror")):
            add((row << 4) | 0x0B, f"_ad = self.dp(self.imm())\nself.wr(_ad, self.{fn}(self.rd(_ad)))", 4)
            add(((row + 1) << 4) | 0x0B, f"_ad = self.dp(self.imm() + self.x)\nself.wr(_ad, self.{fn}(self.rd(_ad)))", 5)
            add((row << 4) | 0x0C, f"_ad = self.imm16()\nself.wr(_ad, self.{fn}(self.rd(_ad)))", 5)
            add(((row + 1) << 4) | 0x0C, f"self.a = self.{fn}(self.a)", 2)
        for row, d in ((8, -1), (0xA, 1)):
            add((row << 4) | 0x0B, f"_ad = self.dp(self.imm())\nself.wr(_ad, self.nz((self.rd(_ad) + {d}) & 0xFF))", 4)
            add(((row + 1) << 4) | 0x0B, f"_ad = self.dp(self.imm() + self.x)\nself.wr(_ad, self.nz((self.rd(_ad) + {d}) & 0xFF))", 5)
            add((row << 4) | 0x0C, f"_ad = self.imm16()\nself.wr(_ad, self.nz((self.rd(_ad) + {d}) & 0xFF))", 5)
            add(((row + 1) << 4) | 0x0C, f"self.a = self.nz((self.a + {d}) & 0xFF)", 2)
        add(0x1D, "self.x = self.nz((self.x - 1) & 0xFF)", 2)
        add(0x3D, "self.x = self.nz((self.x + 1) & 0xFF)", 2)
        add(0xDC, "self.y = self.nz((self.y - 1) & 0xFF)", 2)
        add(0xFC, "self.y = self.nz((self.y + 1) & 0xFF)", 2)
        # 16-bit
        add(0x1A, """_d = self.imm()
_v = (self.rd16dp(_d) - 1) & 0xFFFF
self.wr(self.dp(_d), _v & 0xFF)
self.wr(self.dp(_d + 1), _v >> 8)
self.psw = (self.psw & ~(N | Z)) | (N if _v & 0x8000 else 0) | (0 if _v else Z)""", 6)
        add(0x3A, """_d = self.imm()
_v = (self.rd16dp(_d) + 1) & 0xFFFF
self.wr(self.dp(_d), _v & 0xFF)
self.wr(self.dp(_d + 1), _v >> 8)
self.psw = (self.psw & ~(N | Z)) | (N if _v & 0x8000 else 0) | (0 if _v else Z)""", 6)
        add(0xBA, """_v = self.rd16dp(self.imm())
self.a = _v & 0xFF
self.y = _v >> 8
self.psw = (self.psw & ~(N | Z)) | (N if _v & 0x8000 else 0) | (0 if _v else Z)""", 5)
        add(0xDA, """_d = self.imm()
self.wr(self.dp(_d), self.a)
self.wr(self.dp(_d + 1), self.y)""", 5)
        add(0x5A, """_v = self.rd16dp(self.imm())
_r = ((self.y << 8) | self.a) - _v
self.psw = (self.psw & ~(N | Z | C)) | (C if _r >= 0 else 0) | (N if _r & 0x8000 else 0) | (0 if _r & 0xFFFF else Z)""", 4)
        for op, sign in ((0x7A, 1), (0x9A, -1)):
            add(op, f"""_w = self.rd16dp(self.imm())
_ya = (self.y << 8) | self.a
_b = _w if {sign} > 0 else (_w ^ 0xFFFF)
_c = 0 if {sign} > 0 else 1
_r = _ya + _b + _c
_p = self.psw & ~(N | V | H | Z | C)
if _r > 0xFFFF:
    _p |= C
if (~(_ya ^ _b) & (_ya ^ _r)) & 0x8000:
    _p |= V
if ((_ya & 0xFFF) + (_b & 0xFFF) + _c) > 0xFFF:
    _p |= H
_r &= 0xFFFF
self.psw = _p | (N if _r & 0x8000 else 0) | (0 if _r else Z)
self.a = _r & 0xFF
self.y = _r >> 8""", 5)
        add(0xCF, """_r = self.y * self.a
self.a = _r & 0xFF
self.y = _r >> 8
self.nz(self.y)""", 9)
        add(0x9E, """_ya = (self.y << 8) | self.a
_x = self.x
_p = self.psw & ~(V | H)
if self.y >= _x:
    _p |= V
if (self.y & 0xF) >= (_x & 0xF):
    _p |= H
self.psw = _p
if self.y < (_x << 1):
    self.a = (_ya // _x) & 0xFF
    self.y = (_ya % _x) & 0xFF
else:
    self.a = (255 - (_ya - (_x << 9)) // (256 - _x)) & 0xFF
    self.y = (_x + (_ya - (_x << 9)) % (256 - _x)) & 0xFF
self.nz(self.a)""", 12)
        add(0xDF, """_a = self.a
if (self.psw & C) or _a > 0x99:
    _a += 0x60
    self.psw |= C
if (self.psw & H) or (_a & 0xF) > 9:
    _a += 6
self.a = self.nz(_a & 0xFF)""", 3)
        add(0xBE, """_a = self.a
if not (self.psw & C) or _a > 0x99:
    _a -= 0x60
    self.psw &= ~C
if not (self.psw & H) or (_a & 0xF) > 9:
    _a -= 6
self.a = self.nz(_a & 0xFF)""", 3)
        add(0x9F, "self.a = self.nz(((self.a << 4) | (self.a >> 4)) & 0xFF)", 5)
        # bit operations
        for b in range(8):
            add((b << 5) | 0x02, f"_ad = self.dp(self.imm())\nself.wr(_ad, self.rd(_ad) | {1 << b})", 4)
            add((b << 5) | 0x12, f"_ad = self.dp(self.imm())\nself.wr(_ad, self.rd(_ad) & {0xFF ^ (1 << b)})", 4)
            add((b << 5) | 0x03, f"_v = self.rd(self.dp(self.imm()))\nself.branch(_v & {1 << b})", 5)
            add((b << 5) | 0x13, f"_v = self.rd(self.dp(self.imm()))\nself.branch(not (_v & {1 << b}))", 5)
        bit_ad = "_w = self.imm16()\n_ad = _w & 0x1FFF\n_b = _w >> 13\n_m = (self.rd(_ad) >> _b) & 1"
        add(0x0A, bit_ad + "\nself.psw |= C if _m else 0", 5)
        add(0x2A, bit_ad + "\nself.psw |= 0 if _m else C", 5)
        add(0x4A, bit_ad + "\nif not _m:\n    self.psw &= ~C", 4)
        add(0x6A, bit_ad + "\nif _m:\n    self.psw &= ~C", 4)
        add(0x8A, bit_ad + "\nself.psw ^= C if _m else 0", 5)
        add(0xAA, bit_ad + "\nself.psw = (self.psw & ~C) | _m", 4)
        add(0xCA, bit_ad + "\n_v = self.rd(_ad) & ~(1 << _b)\nself.wr(_ad, _v | ((self.psw & C) << _b))", 6)
        add(0xEA, bit_ad + "\nself.wr(_ad, self.rd(_ad) ^ (1 << _b))", 5)
        add(0x0E, """_ad = self.imm16()
_t = self.rd(_ad)
self.nz((self.a - _t) & 0xFF)
self.wr(_ad, _t | self.a)""", 6)
        add(0x4E, """_ad = self.imm16()
_t = self.rd(_ad)
self.nz((self.a - _t) & 0xFF)
self.wr(_ad, _t & (self.a ^ 0xFF))""", 6)
        # flags
        add(0x20, "self.psw &= ~P", 2)
        add(0x40, "self.psw |= P", 2)
        add(0x60, "self.psw &= ~C", 2)
        add(0x80, "self.psw |= C", 2)
        add(0xA0, "self.psw |= I", 3)
        add(0xC0, "self.psw &= ~I", 3)
        add(0xE0, "self.psw &= ~(V | H)", 2)
        add(0xED, "self.psw ^= C", 3)
        # branches
        conds = {0x10: "not (self.psw & N)", 0x30: "self.psw & N", 0x50: "not (self.psw & V)",
                 0x70: "self.psw & V", 0x90: "not (self.psw & C)", 0xB0: "self.psw & C",
                 0xD0: "not (self.psw & Z)", 0xF0: "self.psw & Z"}
        for op, cond in conds.items():
            add(op, f"self.branch({cond})", 2)
        add(0x2F, "self.branch(True)", 2)
        add(0x2E, "_v = self.rd(self.dp(self.imm()))\nself.branch(self.a != _v)", 5)
        add(0xDE, "_v = self.rd(self.dp(self.imm() + self.x))\nself.branch(self.a != _v)", 6)
        add(0x6E, """_ad = self.dp(self.imm())
_v = (self.rd(_ad) - 1) & 0xFF
self.wr(_ad, _v)
self.branch(_v != 0)""", 5)
        add(0xFE, "self.y = (self.y - 1) & 0xFF\nself.branch(self.y != 0)", 4)
        # jumps / calls
        add(0x5F, "self.pc = self.imm16()", 3)
        add(0x1F, """_ad = (self.imm16() + self.x) & 0xFFFF
self.pc = self.rd(_ad) | (self.rd(_ad + 1) << 8)""", 6)
        add(0x3F, """_ad = self.imm16()
self.push(self.pc >> 8)
self.push(self.pc & 0xFF)
self.pc = _ad""", 8)
        add(0x4F, """_u = self.imm()
self.push(self.pc >> 8)
self.push(self.pc & 0xFF)
self.pc = 0xFF00 | _u""", 6)
        for n in range(16):
            add((n << 4) | 0x01, f"""self.push(self.pc >> 8)
self.push(self.pc & 0xFF)
_ad = 0xFFDE - {2 * n}
self.pc = self.rd(_ad) | (self.rd(_ad + 1) << 8)""", 8)
        add(0x0F, """self.push(self.pc >> 8)
self.push(self.pc & 0xFF)
self.push(self.psw)
self.psw = (self.psw | B) & ~I
self.pc = self.rd(0xFFDE) | (self.rd(0xFFDF) << 8)""", 8)
        add(0x6F, "_lo = self.pop()\nself.pc = _lo | (self.pop() << 8)", 5)
        add(0x7F, "self.psw = self.pop()\n_lo = self.pop()\nself.pc = _lo | (self.pop() << 8)", 6)
        # stack
        add(0x0D, "self.push(self.psw)", 4)
        add(0x2D, "self.push(self.a)", 4)
        add(0x4D, "self.push(self.x)", 4)
        add(0x6D, "self.push(self.y)", 4)
        add(0x8E, "self.psw = self.pop()", 4)
        add(0xAE, "self.a = self.pop()", 4)
        add(0xCE, "self.x = self.pop()", 4)
        add(0xEE, "self.y = self.pop()", 4)
        # misc
        add(0x00, "pass", 2)
        add(0xEF, "self.halted = True\nself.pc = (self.pc - 1) & 0xFFFF", 3)
        add(0xFF, "self.halted = True\nself.pc = (self.pc - 1) & 0xFFFF", 3)

        ns = {"N": N, "V": V, "P": P, "B": B, "H": H, "I": I, "Z": Z, "C": C}
        exec("\n".join(src), ns)
        missing = [f"{op:02X}" for op in range(256) if op not in ops]
        assert not missing, f"unimplemented SPC700 opcodes: {missing}"
        for op in range(256):
            self.ops[op] = ns[ops[op]].__get__(self)
