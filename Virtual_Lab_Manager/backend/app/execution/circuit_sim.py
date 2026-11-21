"""A tiny, safe combinational-logic simulator for `circuit.sim` netlists (no eval()).

Syntax (one statement per line, `#` comments):
    INPUT A B CIN
    OUTPUT SUM COUT
    P = XOR(A, B)
    SUM = XOR(P, CIN)
    COUT = OR(AND(A, B), AND(P, CIN))
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

GATES = {"AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR", "BUF"}
UNARY = {"NOT", "BUF"}
MAX_INPUTS = 10
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TOKEN = re.compile(r"\s*(?:(?P<id>[A-Za-z_][A-Za-z0-9_]*)|(?P<num>[01])|(?P<sym>[(),]))")


class CircuitError(Exception):
    def __init__(self, message: str, line: int = 0, column: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


# Expression tree: ("const", 0|1) | ("ref", name) | ("gate", NAME, [children])
Expr = tuple


@dataclass
class Circuit:
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    wires: dict[str, Expr] = field(default_factory=dict)
    wire_lines: dict[str, int] = field(default_factory=dict)

    @property
    def gate_count(self) -> int:
        def count(e: Expr) -> int:
            if e[0] == "gate":
                return 1 + sum(count(c) for c in e[2])
            return 0

        return sum(count(e) for e in self.wires.values())

    def evaluate(self, values: dict[str, int]) -> dict[str, int]:
        cache: dict[str, int] = {}
        visiting: set[str] = set()

        def ev(e: Expr) -> int:
            kind = e[0]
            if kind == "const":
                return e[1]
            if kind == "ref":
                return sig(e[1])
            name, args = e[1], [ev(a) for a in e[2]]
            if name == "AND":
                return int(all(args))
            if name == "OR":
                return int(any(args))
            if name == "XOR":
                return sum(args) % 2
            if name == "NAND":
                return int(not all(args))
            if name == "NOR":
                return int(not any(args))
            if name == "XNOR":
                return int(sum(args) % 2 == 0)
            if name == "NOT":
                return int(not args[0])
            return args[0]  # BUF

        def sig(name: str) -> int:
            if name in values:
                return values[name]
            if name in cache:
                return cache[name]
            if name in visiting:
                raise CircuitError(f"combinational loop detected through '{name}'", self.wire_lines.get(name, 0))
            if name not in self.wires:
                raise CircuitError(f"signal '{name}' is never driven", 0)
            visiting.add(name)
            cache[name] = ev(self.wires[name])
            visiting.discard(name)
            return cache[name]

        return {o: sig(o) for o in self.outputs}

    def truth_table(self) -> list[tuple[dict[str, int], dict[str, int]]]:
        rows = []
        for combo in itertools.product((0, 1), repeat=len(self.inputs)):
            ins = dict(zip(self.inputs, combo))
            rows.append((ins, self.evaluate(ins)))
        return rows


def _parse_expr(text: str, line_no: int, col_offset: int) -> Expr:
    tokens: list[tuple[str, str, int]] = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise CircuitError(f"unexpected character '{text[pos:pos + 1].strip() or text[pos:]}'", line_no, col_offset + pos + 1)
        kind = m.lastgroup or ""
        tokens.append((kind, m.group(kind), col_offset + m.start(kind) + 1))
        pos = m.end()
    if not tokens:
        raise CircuitError("missing expression after '='", line_no, col_offset + 1)

    i = 0

    def peek() -> tuple[str, str, int] | None:
        return tokens[i] if i < len(tokens) else None

    def expect(sym: str) -> None:
        nonlocal i
        t = peek()
        if not t or t[1] != sym:
            col = t[2] if t else col_offset + len(text) + 1
            raise CircuitError(f"expected '{sym}'", line_no, col)
        i += 1

    def parse() -> Expr:
        nonlocal i
        t = peek()
        if t is None:
            raise CircuitError("unexpected end of expression", line_no, col_offset + len(text) + 1)
        kind, val, col = t
        if kind == "num":
            i += 1
            return ("const", int(val))
        if kind != "id":
            raise CircuitError(f"unexpected '{val}'", line_no, col)
        i += 1
        nxt = peek()
        if nxt and nxt[1] == "(":
            gate = val.upper()
            if gate not in GATES:
                raise CircuitError(f"unknown gate '{val}' (use {', '.join(sorted(GATES))})", line_no, col)
            i += 1
            args = [parse()]
            while peek() and peek()[1] == ",":
                i += 1
                args.append(parse())
            expect(")")
            if gate in UNARY and len(args) != 1:
                raise CircuitError(f"{gate} takes exactly 1 input", line_no, col)
            if gate not in UNARY and len(args) < 2:
                raise CircuitError(f"{gate} needs at least 2 inputs", line_no, col)
            return ("gate", gate, args)
        if val.upper() in GATES:
            raise CircuitError(f"gate '{val}' must be called like {val.upper()}(A, B)", line_no, col)
        return ("ref", val)

    expr = parse()
    if i != len(tokens):
        raise CircuitError(f"unexpected '{tokens[i][1]}'", line_no, tokens[i][2])
    return expr


def _refs(e: Expr) -> list[str]:
    if e[0] == "ref":
        return [e[1]]
    if e[0] == "gate":
        return [r for c in e[2] for r in _refs(c)]
    return []


def parse_circuit(source: str) -> Circuit:
    c = Circuit()
    for line_no, raw in enumerate(source.splitlines(), start=1):
        line = raw.split("#", 1)[0]
        if not line.strip():
            continue
        stripped = line.strip()
        head = stripped.split(None, 1)[0].upper()
        if head in ("INPUT", "INPUTS", "OUTPUT", "OUTPUTS") and "=" not in stripped:
            names = [n for n in re.split(r"[\s,]+", stripped.split(None, 1)[1] if " " in stripped else "") if n]
            if not names:
                raise CircuitError(f"{head} needs at least one signal name", line_no)
            for n in names:
                if not _IDENT.fullmatch(n):
                    raise CircuitError(f"invalid signal name '{n}'", line_no)
                if n in c.inputs or n in c.outputs:
                    raise CircuitError(f"signal '{n}' declared twice", line_no)
            (c.inputs if head.startswith("INPUT") else c.outputs).extend(names)
            continue
        if "=" not in line:
            raise CircuitError("expected 'INPUT ...', 'OUTPUT ...' or 'NAME = GATE(...)'", line_no)
        lhs, rhs = line.split("=", 1)
        name = lhs.strip()
        if not _IDENT.fullmatch(name):
            raise CircuitError(f"invalid signal name '{name}'", line_no, 1)
        if name.upper() in GATES:
            raise CircuitError(f"'{name}' is a gate name and cannot be a signal", line_no, 1)
        if name in c.inputs:
            raise CircuitError(f"cannot assign to input '{name}'", line_no, 1)
        if name in c.wires:
            raise CircuitError(f"'{name}' is driven twice (first on line {c.wire_lines[name]})", line_no, 1)
        c.wires[name] = _parse_expr(rhs, line_no, len(lhs) + 1)
        c.wire_lines[name] = line_no

    if not c.inputs:
        raise CircuitError("no INPUT declared", 1)
    if not c.outputs:
        raise CircuitError("no OUTPUT declared", 1)
    if len(c.inputs) > MAX_INPUTS:
        raise CircuitError(f"at most {MAX_INPUTS} inputs are supported", 1)
    for name, expr in c.wires.items():
        for ref in _refs(expr):
            if ref not in c.inputs and ref not in c.wires:
                raise CircuitError(f"undefined signal '{ref}'", c.wire_lines[name])
    for out in c.outputs:
        if out not in c.wires and out not in c.inputs:
            raise CircuitError(f"output '{out}' is never assigned", 1)
    # detect loops eagerly with an all-zero evaluation
    c.evaluate({i: 0 for i in c.inputs})
    return c
