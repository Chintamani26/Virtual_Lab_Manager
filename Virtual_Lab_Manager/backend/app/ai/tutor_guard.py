"""Prompt guard for the AI Lab Tutor: runs on the student's message before anything reaches the model.

Layers (each one is cheap and deterministic, so it also protects the offline fallback):
1. sanitize: strip control / invisible characters, cap the length.
2. screen: obvious prompt-injection attempts and requests for restricted data (hidden tests, reference solution,
   other students' work) are answered here without calling the model; requests for the full solution are flagged
   and passed on, so the tutor can decline and still help.
The model is the last layer: untrusted text is wrapped in nonce-delimited data blocks (tutor_context.fence) and the
system prompt tells it never to follow instructions found inside them.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MAX_MESSAGE_CHARS = 1000

# zero-width / bidi control characters that can hide text from a human reviewer
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BLANK_LINES = re.compile(r"\n{4,}")


def sanitize(text: str | None) -> str:
    if not text:
        return ""
    text = _CONTROL.sub("", _INVISIBLE.sub("", text)).replace("\r\n", "\n").replace("\r", "\n")
    return _BLANK_LINES.sub("\n\n\n", text).strip()[:MAX_MESSAGE_CHARS]


def _norm(text: str) -> str:
    """Detection form: NFKC folds look-alike characters (full-width letters etc.), whitespace collapsed."""
    text = unicodedata.normalize("NFKC", text).replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", text).lower()


def _any(patterns: list[str]) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns))


_INJECTION = _any([
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,15}\b(all|any|previous|prior|above|earlier|your|system|these|"
    r"those)\b.{0,15}\b(instructions?|rules|prompts?|guidelines|restrictions)\b",
    r"\b(reveal|show|print|repeat|output|display|tell me|what (is|are)|give me)\b.{0,25}\byour\b.{0,20}"
    r"\b(prompt|instructions|rules|guidelines|internal marker|configuration)\b",
    r"\b(system|initial|original|hidden|secret|internal) (prompt|instructions)\b",
    r"\binternal marker\b",
    r"\b(developer|dev|god|admin|debug|jailbreak|dan)\s+mode\b",
    r"\bjailbreak",
    r"\byou are (now|no longer)\b",
    r"\b(pretend|act|behave|roleplay|role-play)\b.{0,20}\b(you are|you're|to be|as)\b.{0,30}"
    r"\b(unrestricted|unfiltered|without (any )?(rules|restrictions|limits)|different (ai|assistant|model)|chatgpt|dan)\b",
    r"<\s*/?\s*(system|assistant|instructions?)\s*>",
    r"\bnew instructions\b",
])

_PEOPLE = (r"(classmates?|classmate's|classmates'|friends?|friend's|friends'|someone else's|other people's|"
           r"(other|another)\s+(students?|person|people|classmates?|batch|group)(?:'s|')?)")
_RESTRICTED: list[tuple[str, re.Pattern, str]] = [
    ("hidden_tests", _any([r"\bhidden (tests?|cases?|checks?)\b", r"\b(grading|private|secret) tests?\b"]),
     "I can't see the hidden tests, and nobody can before grading. They check the same behaviour the brief "
     "describes, usually at the edges. Which unusual inputs could the brief allow that your code hasn't been tried on?"),
    ("reference_solution", _any([
        r"\b(reference|official|teacher's|teachers'|faculty's|instructor's|sir's|ma'am's|mam's)\s+"
        r"(solution|answers?|code|implementation)\b",
        r"\bmodel (solution|answers?)\b",
        r"\banswer\s*key\b",
    ]),
     "I don't have the faculty's reference solution or the answer key, and I wouldn't share one. "
     "I can help you build your own. Which part are you stuck on right now?"),
    ("other_students", _any([
        rf"\b{_PEOPLE}\s+(code|submissions?|answers?|work|solutions?|programs?)\b",
        rf"\b(code|submissions?|answers?|solutions?) (of|from) (an)?{_PEOPLE}",
    ]),
     "I only see your own work for this lab, never anyone else's. "
     "Tell me what you've tried so far and we'll work from there."),
]

_SOLUTION = _any([
    r"\b(write|give|send|show|paste|provide|generate|complete|finish)\b.{0,20}\b(the|a|my|full|whole|entire|complete|"
    r"correct|working|final)\b.{0,15}\b(code|solution|program|function|implementation|answers?)\b",
    r"\b(solve|do|finish|complete|fix)\b.{0,15}\b(it|this|the (lab|assignment|question|problem)|my (code|lab|"
    r"assignment))\b.{0,15}\bfor me\b",
    r"\bjust (give|tell|show) me (the )?(answer|code|solution|value)\b",
    r"\bwhat (is|are) the (correct |right |final )?(answers?|values?|code)\b",
])

INJECTION_REPLY = ("I'm your tutor for this lab and I keep to its rules. Ask me about the brief, your code, a test "
                   "or a concept, and I'll help you work it out.")


@dataclass
class GuardResult:
    text: str
    flags: list[str] = field(default_factory=list)
    block_reply: str | None = None  # answer with this and skip the model


def screen(message: str | None) -> GuardResult:
    text = sanitize(message)
    if not text:
        return GuardResult(text="")
    norm = _norm(text)
    if _INJECTION.search(norm):
        return GuardResult(text=text, flags=["injection"], block_reply=INJECTION_REPLY)
    for key, pattern, reply in _RESTRICTED:
        if pattern.search(norm):
            return GuardResult(text=text, flags=["restricted", key], block_reply=reply)
    if _SOLUTION.search(norm):
        return GuardResult(text=text, flags=["solution_request"])
    return GuardResult(text=text)
