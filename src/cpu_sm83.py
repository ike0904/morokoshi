"""
Game Boy CPU core (Sharp SM83 / LR35902) for GBS playback (register logging, v0.1.27).

Memory access is delegated to a bus object with read(addr) / write(addr, value).
Cycles are counted in T-states (4.194304 MHz). Interrupts are not emulated: the GBS player
calls INIT / PLAY directly. HALT and STOP end the current call (see gbs.py).
RST n jumps to rst_base + n (GBS: the load address, as in the GBS spec and libgme).
Undefined opcodes set `jammed`.
"""

ZF, NF, HF, CF = 0x80, 0x40, 0x20, 0x10

R8 = ("b", "c", "d", "e", "h", "l", None, "a")     # index 6 = (HL)


class CPUSM83:
    def __init__(self, bus):
        self.bus = bus
        self.a = self.f = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.sp = 0xFFFE
        self.pc = 0
        self.cycles = 0
        self.jammed = False
        self.halted = False
        self.rst_base = 0
        self.ops = [None] * 256
        self.cb = [None] * 256
        self._build()

    # ------------------------------------------------------------------ helpers
    def push(self, v):
        self.sp = (self.sp - 1) & 0xFFFF
        self.bus.write(self.sp, (v >> 8) & 0xFF)
        self.sp = (self.sp - 1) & 0xFFFF
        self.bus.write(self.sp, v & 0xFF)

    def pop(self):
        rd = self.bus.read
        lo = rd(self.sp)
        hi = rd((self.sp + 1) & 0xFFFF)
        self.sp = (self.sp + 2) & 0xFFFF
        return lo | (hi << 8)

    def imm8(self):
        v = self.bus.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def imm16(self):
        rd = self.bus.read
        v = rd(self.pc) | (rd((self.pc + 1) & 0xFFFF) << 8)
        self.pc = (self.pc + 2) & 0xFFFF
        return v

    def step(self):
        op = self.bus.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        self.ops[op]()

    # ------------------------------------------------------------ table builder
    def _build(self):
        """Opcode handlers are generated as Python source (one function per opcode) so the
        regular blocks (LD r,r' / ALU / CB) stay short and fast."""
        src = []
        ops = {}
        cbs = {}

        def rd(i):
            return "self.bus.read((self.h << 8) | self.l)" if i == 6 else f"self.{R8[i]}"

        def wr(i, v):
            return f"self.bus.write((self.h << 8) | self.l, {v})" if i == 6 else f"self.{R8[i]} = {v}"

        def add(op, body, cyc, table=ops):
            name = f"{'cb' if table is cbs else 'op'}_{op:02x}"
            lines = "\n".join("    " + ln for ln in body.strip("\n").split("\n"))
            src.append(f"def {name}(self):\n{lines}\n    self.cycles += {cyc}\n")
            table[op] = name

        pairs = {0: ("b", "c"), 1: ("d", "e"), 2: ("h", "l")}

        def get16(i):
            if i == 3:
                return "self.sp"
            hi, lo = pairs[i]
            return f"((self.{hi} << 8) | self.{lo})"

        def set16(i, v):
            if i == 3:
                return f"self.sp = ({v}) & 0xFFFF"
            hi, lo = pairs[i]
            return f"_v = ({v}) & 0xFFFF\nself.{hi} = _v >> 8\nself.{lo} = _v & 0xFF"

        add(0x00, "pass", 4)
        for i in range(4):
            add(0x01 + 16 * i, set16(i, "self.imm16()"), 12)
            add(0x03 + 16 * i, set16(i, get16(i) + " + 1"), 8)
            add(0x0B + 16 * i, set16(i, get16(i) + " - 1"), 8)
            add(0x09 + 16 * i, f"""_hl = (self.h << 8) | self.l
_r = {get16(i)}
_s = _hl + _r
self.f = (self.f & 0x80) | (0x20 if (_hl & 0xFFF) + (_r & 0xFFF) > 0xFFF else 0) | (0x10 if _s > 0xFFFF else 0)
self.h = (_s >> 8) & 0xFF
self.l = _s & 0xFF""", 8)
        add(0x02, "self.bus.write((self.b << 8) | self.c, self.a)", 8)
        add(0x12, "self.bus.write((self.d << 8) | self.e, self.a)", 8)
        add(0x0A, "self.a = self.bus.read((self.b << 8) | self.c)", 8)
        add(0x1A, "self.a = self.bus.read((self.d << 8) | self.e)", 8)
        for op, w, dlt in ((0x22, True, 1), (0x32, True, -1), (0x2A, False, 1), (0x3A, False, -1)):
            mem = "self.bus.write(_hl, self.a)" if w else "self.a = self.bus.read(_hl)"
            add(op, f"""_hl = (self.h << 8) | self.l
{mem}
_hl = (_hl + {dlt}) & 0xFFFF
self.h = _hl >> 8
self.l = _hl & 0xFF""", 8)

        for i in range(8):
            heavy = i == 6
            add(0x04 + 8 * i, f"""_v = ({rd(i)} + 1) & 0xFF
{wr(i, '_v')}
self.f = (self.f & 0x10) | (0x80 if _v == 0 else 0) | (0x20 if (_v & 0xF) == 0 else 0)""", 12 if heavy else 4)
            add(0x05 + 8 * i, f"""_v = ({rd(i)} - 1) & 0xFF
{wr(i, '_v')}
self.f = (self.f & 0x10) | 0x40 | (0x80 if _v == 0 else 0) | (0x20 if (_v & 0xF) == 0xF else 0)""", 12 if heavy else 4)
            add(0x06 + 8 * i, wr(i, "self.imm8()"), 12 if heavy else 8)

        add(0x07, """_a = self.a
_c = _a >> 7
self.a = ((_a << 1) | _c) & 0xFF
self.f = 0x10 if _c else 0""", 4)
        add(0x0F, """_a = self.a
_c = _a & 1
self.a = (_a >> 1) | (_c << 7)
self.f = 0x10 if _c else 0""", 4)
        add(0x17, """_a = self.a
_c = _a >> 7
self.a = ((_a << 1) | (1 if self.f & 0x10 else 0)) & 0xFF
self.f = 0x10 if _c else 0""", 4)
        add(0x1F, """_a = self.a
_c = _a & 1
self.a = (_a >> 1) | (0x80 if self.f & 0x10 else 0)
self.f = 0x10 if _c else 0""", 4)
        add(0x08, """_ad = self.imm16()
self.bus.write(_ad, self.sp & 0xFF)
self.bus.write((_ad + 1) & 0xFFFF, self.sp >> 8)""", 20)
        add(0x10, "self.pc = (self.pc + 1) & 0xFFFF\nself.halted = True", 4)
        add(0x18, "_e = self.imm8()\nself.pc = (self.pc + (_e - 256 if _e > 127 else _e)) & 0xFFFF", 12)
        conds = ("not (self.f & 0x80)", "self.f & 0x80", "not (self.f & 0x10)", "self.f & 0x10")
        for k, cond in enumerate(conds):
            add(0x20 + 8 * k, f"""_e = self.imm8()
if {cond}:
    self.pc = (self.pc + (_e - 256 if _e > 127 else _e)) & 0xFFFF
    self.cycles += 4""", 8)
            add(0xC0 + 8 * k, f"""if {cond}:
    self.pc = self.pop()
    self.cycles += 12""", 8)
            add(0xC2 + 8 * k, f"""_ad = self.imm16()
if {cond}:
    self.pc = _ad
    self.cycles += 4""", 12)
            add(0xC4 + 8 * k, f"""_ad = self.imm16()
if {cond}:
    self.push(self.pc)
    self.pc = _ad
    self.cycles += 12""", 12)
        add(0x27, """_a = self.a
_f = self.f
if not (_f & 0x40):
    if (_f & 0x10) or _a > 0x99:
        _a += 0x60
        _f |= 0x10
    if (_f & 0x20) or (_a & 0xF) > 9:
        _a += 6
else:
    if _f & 0x10:
        _a -= 0x60
    if _f & 0x20:
        _a -= 6
_a &= 0xFF
self.a = _a
self.f = (_f & 0x50) | (0x80 if _a == 0 else 0)""", 4)
        add(0x2F, "self.a ^= 0xFF\nself.f |= 0x60", 4)
        add(0x37, "self.f = (self.f & 0x80) | 0x10", 4)
        add(0x3F, "self.f = (self.f & 0x80) | ((self.f & 0x10) ^ 0x10)", 4)

        for dst in range(8):
            for s in range(8):
                op = 0x40 + 8 * dst + s
                if op == 0x76:
                    add(op, "self.halted = True", 4)
                    continue
                add(op, wr(dst, rd(s)), 8 if (dst == 6 or s == 6) else 4)

        alu = (
            # ADD
            """_a = self.a
_r = _a + _v
self.a = _r & 0xFF
self.f = (0x80 if self.a == 0 else 0) | (0x20 if (_a & 0xF) + (_v & 0xF) > 0xF else 0) | (0x10 if _r > 0xFF else 0)""",
            # ADC
            """_a = self.a
_c = 1 if self.f & 0x10 else 0
_r = _a + _v + _c
self.a = _r & 0xFF
self.f = (0x80 if self.a == 0 else 0) | (0x20 if (_a & 0xF) + (_v & 0xF) + _c > 0xF else 0) | (0x10 if _r > 0xFF else 0)""",
            # SUB
            """_a = self.a
_r = _a - _v
self.a = _r & 0xFF
self.f = 0x40 | (0x80 if self.a == 0 else 0) | (0x20 if (_a & 0xF) < (_v & 0xF) else 0) | (0x10 if _r < 0 else 0)""",
            # SBC
            """_a = self.a
_c = 1 if self.f & 0x10 else 0
_r = _a - _v - _c
self.a = _r & 0xFF
self.f = 0x40 | (0x80 if self.a == 0 else 0) | (0x20 if (_a & 0xF) < (_v & 0xF) + _c else 0) | (0x10 if _r < 0 else 0)""",
            # AND
            """self.a &= _v
self.f = 0x20 | (0x80 if self.a == 0 else 0)""",
            # XOR
            """self.a ^= _v
self.f = 0x80 if self.a == 0 else 0""",
            # OR
            """self.a |= _v
self.f = 0x80 if self.a == 0 else 0""",
            # CP
            """_a = self.a
_r = _a - _v
self.f = 0x40 | (0x80 if _r == 0 else 0) | (0x20 if (_a & 0xF) < (_v & 0xF) else 0) | (0x10 if _r < 0 else 0)""",
        )
        for k, body in enumerate(alu):
            for s in range(8):
                add(0x80 + 8 * k + s, f"_v = {rd(s)}\n{body}", 8 if s == 6 else 4)
            add(0xC6 + 8 * k, f"_v = self.imm8()\n{body}", 8)

        for k, (hi, lo) in enumerate((("b", "c"), ("d", "e"), ("h", "l"))):
            add(0xC1 + 16 * k, f"_v = self.pop()\nself.{hi} = _v >> 8\nself.{lo} = _v & 0xFF", 12)
            add(0xC5 + 16 * k, f"self.push((self.{hi} << 8) | self.{lo})", 16)
        add(0xF1, "_v = self.pop()\nself.a = _v >> 8\nself.f = _v & 0xF0", 12)
        add(0xF5, "self.push((self.a << 8) | self.f)", 16)
        add(0xC3, "self.pc = self.imm16()", 16)
        add(0xCD, "_ad = self.imm16()\nself.push(self.pc)\nself.pc = _ad", 24)
        add(0xC9, "self.pc = self.pop()", 16)
        add(0xD9, "self.pc = self.pop()", 16)
        for n in range(8):
            add(0xC7 + 8 * n, f"self.push(self.pc)\nself.pc = (self.rst_base + {8 * n}) & 0xFFFF", 16)
        add(0xE0, "self.bus.write(0xFF00 | self.imm8(), self.a)", 12)
        add(0xF0, "self.a = self.bus.read(0xFF00 | self.imm8())", 12)
        add(0xE2, "self.bus.write(0xFF00 | self.c, self.a)", 8)
        add(0xF2, "self.a = self.bus.read(0xFF00 | self.c)", 8)
        add(0xEA, "self.bus.write(self.imm16(), self.a)", 16)
        add(0xFA, "self.a = self.bus.read(self.imm16())", 16)
        sp_e = """_e = self.imm8()
_sp = self.sp
self.f = (0x20 if (_sp & 0xF) + (_e & 0xF) > 0xF else 0) | (0x10 if (_sp & 0xFF) + _e > 0xFF else 0)
_r = (_sp + (_e - 256 if _e > 127 else _e)) & 0xFFFF"""
        add(0xE8, sp_e + "\nself.sp = _r", 16)
        add(0xF8, sp_e + "\nself.h = _r >> 8\nself.l = _r & 0xFF", 12)
        add(0xF9, "self.sp = (self.h << 8) | self.l", 8)
        add(0xE9, "self.pc = (self.h << 8) | self.l", 4)
        add(0xF3, "pass", 4)
        add(0xFB, "pass", 4)
        add(0xCB, "_op = self.imm8()\nself.cb[_op]()", 0)
        for op in (0xD3, 0xDB, 0xDD, 0xE3, 0xE4, 0xEB, 0xEC, 0xED, 0xF4, 0xFC, 0xFD):
            add(op, "self.jammed = True\nself.pc = (self.pc - 1) & 0xFFFF", 4)

        rot = (
            "_c = _v >> 7\n_r = ((_v << 1) | _c) & 0xFF",                                   # RLC
            "_c = _v & 1\n_r = (_v >> 1) | (_c << 7)",                                       # RRC
            "_c = _v >> 7\n_r = ((_v << 1) | (1 if self.f & 0x10 else 0)) & 0xFF",          # RL
            "_c = _v & 1\n_r = (_v >> 1) | (0x80 if self.f & 0x10 else 0)",                 # RR
            "_c = _v >> 7\n_r = (_v << 1) & 0xFF",                                          # SLA
            "_c = _v & 1\n_r = (_v >> 1) | (_v & 0x80)",                                    # SRA
            "_c = 0\n_r = ((_v << 4) | (_v >> 4)) & 0xFF",                                  # SWAP
            "_c = _v & 1\n_r = _v >> 1",                                                    # SRL
        )
        for k, body in enumerate(rot):
            for s in range(8):
                add(8 * k + s, f"""_v = {rd(s)}
{body}
{wr(s, '_r')}
self.f = (0x80 if _r == 0 else 0) | (0x10 if _c else 0)""", 16 if s == 6 else 8, cbs)
        for bit in range(8):
            for s in range(8):
                add(0x40 + 8 * bit + s, f"self.f = (self.f & 0x10) | 0x20 | (0 if {rd(s)} & {1 << bit} else 0x80)",
                    12 if s == 6 else 8, cbs)
                add(0x80 + 8 * bit + s, wr(s, f"{rd(s)} & {0xFF ^ (1 << bit)}"), 16 if s == 6 else 8, cbs)
                add(0xC0 + 8 * bit + s, wr(s, f"{rd(s)} | {1 << bit}"), 16 if s == 6 else 8, cbs)

        ns = {}
        exec("\n".join(src), ns)
        missing = [op for op in range(256) if op not in ops] + [op for op in range(256) if op not in cbs]
        assert not missing, f"unimplemented opcodes: {missing}"
        for op in range(256):
            self.ops[op] = ns[ops[op]].__get__(self)
            self.cb[op] = ns[cbs[op]].__get__(self)
