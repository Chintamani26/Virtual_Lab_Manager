"""Unified execution schema shared by every lab adapter (coding / circuit / notebook)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

from app.models import LabType, TestCaseSpec, TestResult

RunStatus = Literal["ok", "error", "timeout", "compile_error"]
ExecMode = Literal["run", "test"]

MAX_OUTPUT_CHARS = 64_000


def clip(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [output truncated, {len(text) - limit} more characters]"


class RawRunResult(BaseModel):
    """What a sandbox runner returns for one Python program."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    status: RunStatus = "ok"
    duration_ms: int = 0
    engine: str


class CellOutput(BaseModel):
    index: int
    stdout: str = ""
    error: str | None = None


class TruthTableRow(BaseModel):
    inputs: dict[str, int]
    outputs: dict[str, int]


class ExecutionRequest(BaseModel):
    lab_type: LabType
    files: dict[str, str]
    mode: ExecMode = "test"
    tests: list[TestCaseSpec] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    execution_id: str | None = None
    engine: str
    lab_type: LabType
    mode: ExecMode
    status: RunStatus
    stdout: str = ""
    stderr: str = ""
    tests: list[TestResult] = Field(default_factory=list)
    tests_passed: int = 0
    tests_total: int = 0
    duration_ms: int = 0
    cell_outputs: list[CellOutput] | None = None
    truth_table: list[TruthTableRow] | None = None
    summary: str = ""

    def finalize(self) -> "ExecutionResult":
        self.tests_total = len(self.tests)
        self.tests_passed = sum(1 for t in self.tests if t.passed)
        if self.mode == "test":
            self.summary = f"{self.tests_passed} of {self.tests_total} Tests Passed"
            if self.status == "timeout":
                self.summary += " (time limit exceeded)"
            elif self.status == "compile_error":
                self.summary += " (code failed to load)"
        else:
            self.summary = {
                "ok": "Program finished successfully",
                "error": "Program exited with an error",
                "timeout": "Time limit exceeded",
                "compile_error": "Compilation / syntax error",
            }[self.status]
        return self


class PythonRunner(ABC):
    """Sandbox that executes a single, self-contained Python 3 program."""

    name: str = "runner"

    @abstractmethod
    async def run(self, source: str, stdin: str = "") -> RawRunResult: ...


class LabAdapter(ABC):
    """Translate one lab type into executions and normalized results."""

    lab_type: LabType
    filename: str

    @abstractmethod
    async def execute(self, req: ExecutionRequest) -> ExecutionResult: ...
