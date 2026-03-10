"""Best-effort structural extraction for hidden URLs and domains."""

from __future__ import annotations

import ast
import codecs
import re
import textwrap
from urllib.parse import unquote

from skrisk.analysis.deobfuscator import extract_base64_segments

_PERCENT_ESCAPE_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_UNICODE_ESCAPE_RE = re.compile(r"\\u[0-9A-Fa-f]{4}|\\x[0-9A-Fa-f]{2}")
_CHARCODE_RE = re.compile(
    r"String\.fromCharCode\(\s*([0-9,\s]+)\s*\)",
    re.IGNORECASE,
)
_SHELL_ASSIGNMENT_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(?:\"([^\"]*)\"|'([^']*)')\s*$",
    re.MULTILINE,
)
_BARE_DOMAIN_RE = re.compile(
    r"(?<![@/A-Za-z0-9_-])((?:[A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,63})(?![A-Za-z0-9_-])"
)


def expand_text_variants(text: str) -> list[tuple[str, str]]:
    """Return unique decoded/expanded variants of a source text."""

    variants: list[tuple[str, str]] = [("original", text)]

    for decoded in extract_base64_segments(text):
        _append_variant(variants, "decoded-base64", decoded)

    if _PERCENT_ESCAPE_RE.search(text):
        decoded = unquote(text)
        if decoded != text:
            _append_variant(variants, "decoded-percent", decoded)

    if _UNICODE_ESCAPE_RE.search(text):
        try:
            decoded = codecs.decode(text, "unicode_escape")
        except Exception:
            decoded = text
        if decoded != text:
            _append_variant(variants, "decoded-unicode", decoded)

    for decoded in _extract_charcode_segments(text):
        _append_variant(variants, "decoded-charcode", decoded)

    for reconstructed in _extract_python_strings(text):
        _append_variant(variants, "python-structure", reconstructed)

    for reconstructed in _extract_javascript_strings(text):
        _append_variant(variants, "javascript-structure", reconstructed)

    for reconstructed in _extract_shell_strings(text):
        _append_variant(variants, "shell-structure", reconstructed)

    return variants


def extract_bare_domains(text: str) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for match in _BARE_DOMAIN_RE.finditer(text):
        value = match.group(1).lower()
        if value in seen:
            continue
        seen.add(value)
        domains.append(value)
    return domains


def _append_variant(variants: list[tuple[str, str]], kind: str, value: str) -> None:
    normalized = value.strip()
    if not normalized:
        return
    if any(existing == normalized for _, existing in variants):
        return
    variants.append((kind, normalized))


def _extract_charcode_segments(text: str) -> list[str]:
    extracted: list[str] = []
    for match in _CHARCODE_RE.finditer(text):
        values = []
        for raw in match.group(1).split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                values.append(int(raw))
            except ValueError:
                values = []
                break
        if not values:
            continue
        try:
            extracted.append("".join(chr(value) for value in values))
        except ValueError:
            continue
    return extracted


class _PythonStringCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self._env: dict[str, str] = {}
        self.extracted: list[str] = []

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        value = self._eval(node.value)
        if value is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._env[target.id] = value
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        for argument in node.args:
            value = self._eval(argument)
            if value:
                self.extracted.append(value)
        self.generic_visit(node)

    def _eval(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self._env.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._eval(node.left)
            right = self._eval(node.right)
            if left is not None and right is not None:
                return left + right
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue):
                    nested = self._eval(value.value)
                    if nested is None:
                        return None
                    parts.append(nested)
            return "".join(parts)
        return None


def _extract_python_strings(text: str) -> list[str]:
    try:
        tree = ast.parse(textwrap.dedent(text))
    except SyntaxError:
        return []
    collector = _PythonStringCollector()
    collector.visit(tree)
    return collector.extracted


def _extract_javascript_strings(text: str) -> list[str]:
    env: dict[str, str] = {}
    extracted: list[str] = []

    for name, value in _extract_js_assignments(text).items():
        env[name] = value
        extracted.append(value)

    for expression in re.findall(r"(?:fetch|axios\.(?:get|post)|XMLHttpRequest\.open)\(([^)]+)\)", text):
        value = _eval_js_concat(expression, env)
        if value:
            extracted.append(value)

    return extracted


def _extract_js_assignments(text: str) -> dict[str, str]:
    env: dict[str, str] = {}
    assignment_re = re.compile(
        r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(.+?);",
        re.DOTALL,
    )
    for name, expression in assignment_re.findall(text):
        value = _eval_js_concat(expression, env)
        if value is not None:
            env[name] = value
    return env


def _eval_js_concat(expression: str, env: dict[str, str]) -> str | None:
    parts = [part.strip() for part in expression.split("+")]
    if len(parts) == 1:
        return _eval_js_atom(parts[0], env)
    resolved: list[str] = []
    for part in parts:
        value = _eval_js_atom(part, env)
        if value is None:
            return None
        resolved.append(value)
    return "".join(resolved)


def _eval_js_atom(part: str, env: dict[str, str]) -> str | None:
    part = part.strip().rstrip(",")
    if not part:
        return ""
    if (part.startswith('"') and part.endswith('"')) or (part.startswith("'") and part.endswith("'")):
        return part[1:-1]
    charcode_match = _CHARCODE_RE.fullmatch(part)
    if charcode_match:
        joined = _extract_charcode_segments(part)
        return joined[0] if joined else None
    return env.get(part)


def _extract_shell_strings(text: str) -> list[str]:
    env: dict[str, str] = {}
    extracted: list[str] = []
    for name, dq_value, sq_value in _SHELL_ASSIGNMENT_RE.findall(text):
        value = dq_value or sq_value
        env[name] = value
        extracted.append(value)

    command_re = re.compile(r"(?:curl|wget)\s+([^\n|;]+)")
    for expression in command_re.findall(text):
        value = _resolve_shell_expression(expression.strip(), env)
        if value:
            extracted.append(value)
    return extracted


def _resolve_shell_expression(expression: str, env: dict[str, str]) -> str | None:
    parts = re.split(r"(\$[A-Za-z_][A-Za-z0-9_]*)", expression)
    resolved: list[str] = []
    changed = False
    for part in parts:
        if not part:
            continue
        if part.startswith("$"):
            name = part[1:]
            value = env.get(name)
            if value is None:
                return None
            resolved.append(value)
            changed = True
        else:
            resolved.append(part)
    if not changed:
        return expression
    return "".join(resolved)
