"""Hybrid linting: instant local checks (ast / circuit parser) + cached Gemma suggestions."""

from __future__ import annotations

import ast
import hashlib
import json
from collections import OrderedDict
from typing import Literal

from pydantic import BaseModel

from app.ai import prompts
from app.ai.client import AIClient
from app.execution.circuit_sim import CircuitError, parse_circuit
from app.schemas import LintDiagnostic, LintResponse

_CACHE_MAX = 512
_GEMMA_MAX_CHARS = 20_000


class _GemmaDiag(BaseModel):
    line: int
    severity: Literal["warning", "info", "error"] = "warning"
    message: str


class _GemmaOut(BaseModel):
    diagnostics: list[_GemmaDiag] = []


def _python_checks(src: str, line_offset_label: str = "") -> list[LintDiagnostic]:
    prefix = f"[{line_offset_label}] " if line_offset_label else ""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [LintDiagnostic(line=e.lineno or 1, column=e.offset or 1, severity="error",
                               message=f"{prefix}SyntaxError: {e.msg}", source="syntax")]
    diags: list[LintDiagnostic] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant) and comp.value is None:
                    diags.append(LintDiagnostic(line=node.lineno, column=node.col_offset + 1, severity="info",
                                                message=f"{prefix}Use `is None` / `is not None` to compare with None.",
                                                source="syntax"))
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            diags.append(LintDiagnostic(line=node.lineno, column=node.col_offset + 1, severity="warning",
                                        message=f"{prefix}Bare `except:` hides real errors — catch a specific exception.",
                                        source="syntax"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.args.defaults:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    diags.append(LintDiagnostic(line=d.lineno, column=d.col_offset + 1, severity="warning",
                                                message=f"{prefix}Mutable default argument in `{node.name}` is shared between calls.",
                                                source="syntax"))
    return diags


class HybridLinter:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai
        self._cache: OrderedDict[str, list[LintDiagnostic]] = OrderedDict()

    def _cache_get(self, key: str) -> list[LintDiagnostic] | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key: str, value: list[LintDiagnostic]) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > _CACHE_MAX:
            self._cache.popitem(last=False)

    async def lint(self, lab_type: str, filename: str, source: str) -> LintResponse:
        if lab_type == "worksheet":
            return LintResponse(diagnostics=[], model="local")  # numeric answers: nothing to lint
        if lab_type == "circuit" or filename.endswith(".sim"):
            try:
                parse_circuit(source)
                return LintResponse(diagnostics=[], model="circuit-parser")
            except CircuitError as e:
                return LintResponse(
                    diagnostics=[LintDiagnostic(line=max(1, e.line), column=e.column, severity="error",
                                                message=e.message, source="circuit")],
                    model="circuit-parser",
                )

        if lab_type == "notebook" or filename.endswith(".ipynb"):
            try:
                cells = json.loads(source).get("cells", [])
            except (json.JSONDecodeError, AttributeError):
                return LintResponse(diagnostics=[LintDiagnostic(line=1, severity="error", message="Notebook JSON is invalid",
                                                                source="syntax")], model="local")
            diags: list[LintDiagnostic] = []
            for idx, cell in enumerate(cells):
                if cell.get("cell_type") == "code":
                    src = cell.get("source", "")
                    src = "".join(src) if isinstance(src, list) else src
                    src = "\n".join(("# " + ln) if ln.lstrip().startswith(("%", "!")) else ln for ln in src.splitlines())
                    diags.extend(_python_checks(src, f"cell {idx}"))
            return LintResponse(diagnostics=diags, model="local")

        # coding: local checks first; Gemma only when the code parses
        local = _python_checks(source)
        if any(d.severity == "error" for d in local) or not self.ai.enabled or len(source) > _GEMMA_MAX_CHARS:
            return LintResponse(diagnostics=local, model="local")

        key = hashlib.sha256(source.encode()).hexdigest()
        cached = self._cache_get(key)
        if cached is not None:
            return LintResponse(diagnostics=local + cached, model=self.ai.gemma_model, cached=True)

        numbered = "\n".join(f"{i:>4}| {line}" for i, line in enumerate(source.splitlines(), start=1))
        out = await self.ai.gemma_json(system=prompts.GEMMA_LINTER, prompt=f"File: {filename}\n\n{numbered}", schema=_GemmaOut)
        if out is None:
            return LintResponse(diagnostics=local, model="local")
        n_lines = max(1, source.count("\n") + 1)
        gemma = [
            LintDiagnostic(line=min(max(1, d.line), n_lines), column=1,
                           severity="warning" if d.severity == "error" else d.severity,
                           message=d.message[:300], source="gemma")
            for d in out.diagnostics[:5]
        ]
        self._cache_put(key, gemma)
        return LintResponse(diagnostics=local + gemma, model=self.ai.gemma_model)
