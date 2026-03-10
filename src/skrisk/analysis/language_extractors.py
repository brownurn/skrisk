"""Best-effort structural extraction for hidden URLs and domains."""

from __future__ import annotations

import ast
import base64
import binascii
import codecs
from pathlib import Path
import re
import textwrap
from urllib.parse import unquote

import bashlex
import esprima
import tldextract

from skrisk.analysis.deobfuscator import (
    extract_base64_segments,
    extract_hex_segments,
    extract_powershell_encoded_segments,
)

_PERCENT_ESCAPE_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_UNICODE_ESCAPE_RE = re.compile(r"\\u[0-9A-Fa-f]{4}|\\x[0-9A-Fa-f]{2}")
_CHARCODE_RE = re.compile(
    r"String\.fromCharCode\(\s*([0-9,\s]+)\s*\)",
    re.IGNORECASE,
)
_MARKDOWN_FENCE_RE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~")
_MARKDOWN_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_SHELL_ASSIGNMENT_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(?:\"([^\"]*)\"|'([^']*)')\s*$",
    re.MULTILINE,
)
_BARE_DOMAIN_RE = re.compile(
    r"(?<![@./A-Za-z0-9_-])((?:[A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,63})(?![A-Za-z0-9_-])"
)
_FILELIKE_SUFFIXES = {
    "csv",
    "css",
    "docx",
    "gif",
    "html",
    "jpeg",
    "jpg",
    "js",
    "json",
    "jsx",
    "lock",
    "log",
    "md",
    "pdf",
    "png",
    "pptx",
    "py",
    "sh",
    "skill",
    "sql",
    "svg",
    "toml",
    "ts",
    "tsx",
    "txt",
    "webp",
    "xlsx",
    "xml",
    "yaml",
    "yml",
}
_CODELIKE_SUFFIXES = {
    "append",
    "argumentparser",
    "args",
    "decode",
    "dumps",
    "dump",
    "encode",
    "endswith",
    "extend",
    "filesystem",
    "findall",
    "get",
    "items",
    "keys",
    "jsondecodeerror",
    "kill",
    "load",
    "loads",
    "lower",
    "match",
    "mkdir",
    "model",
    "name",
    "localecompare",
    "open",
    "parent",
    "path",
    "popen",
    "procfs",
    "read",
    "replace",
    "resolve",
    "result",
    "run",
    "save",
    "search",
    "split",
    "startswith",
    "stderr",
    "statuscode",
    "stdin",
    "stdout",
    "strip",
    "sysfs",
    "timeoutexpired",
    "upper",
    "value",
    "values",
    "wait",
    "write",
}
_RESERVED_DOMAIN_SUFFIXES = {
    "example.com",
    "example.net",
    "example.org",
}
_LOW_SIGNAL_HOSTS = {
    "localhost",
}
_TEXT_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=None)


def expand_text_variants(text: str) -> list[tuple[str, str]]:
    """Return unique decoded/expanded variants of a source text."""

    variants: list[tuple[str, str]] = []
    queue: list[tuple[str, str]] = [("original", text)]
    seen_texts: set[str] = set()

    while queue and len(variants) < 64:
        variant_kind, variant_text = queue.pop(0)
        normalized = variant_text.strip()
        if not normalized or normalized in seen_texts:
            continue
        seen_texts.add(normalized)
        variants.append((variant_kind, normalized))

        for next_kind, next_value in _expand_once(variant_text):
            if next_value.strip() and next_value.strip() not in seen_texts:
                queue.append((next_kind, next_value))

    return variants


def extract_bare_domains(text: str, *, source_path: str | None = None) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    candidate_text = _prepare_text_for_bare_domains(text, source_path=source_path)
    for match in _BARE_DOMAIN_RE.finditer(candidate_text):
        value = match.group(1).lower()
        if _should_ignore_domain_context(candidate_text, match.start(1), match.end(1)):
            continue
        if _should_ignore_domain_like_token(value):
            continue
        if value in seen:
            continue
        seen.add(value)
        domains.append(value)
    return domains


def is_meaningful_domain_candidate(value: str) -> bool:
    return not _should_ignore_domain_like_token(value)


def _should_ignore_domain_like_token(value: str) -> bool:
    lowered = value.lower()
    if any(token in lowered for token in ("${", "}", "`", "<", ">", "(", ")", "[", "]")):
        return True
    if lowered in _LOW_SIGNAL_HOSTS or lowered.endswith(".localhost"):
        return True
    if any(lowered == suffix or lowered.endswith(f".{suffix}") for suffix in _RESERVED_DOMAIN_SUFFIXES):
        return True
    if lowered.startswith("your-") or ".your-" in lowered:
        return True

    labels = value.split(".")
    if any(not label or label.startswith("-") or label.endswith("-") for label in labels):
        return True
    if len(labels) == 2 and len(labels[0]) == 1:
        return True

    extracted = _TEXT_EXTRACTOR(lowered)
    has_public_suffix = bool(extracted.domain and extracted.suffix)

    suffix = value.rsplit(".", 1)[-1]
    if len(labels) == 2 and (_is_code_like_label(labels[0]) or suffix in _FILELIKE_SUFFIXES or suffix in _CODELIKE_SUFFIXES):
        return True
    if not has_public_suffix and (suffix in _FILELIKE_SUFFIXES or suffix in _CODELIKE_SUFFIXES):
        return True

    code_like_label_count = sum(_is_code_like_label(label) for label in labels)
    if code_like_label_count >= max(2, len(labels) - 1):
        return True
    return False


def _should_ignore_domain_context(text: str, start: int, end: int) -> bool:
    prefix = text[max(0, start - 3):start]
    suffix = text[end:min(len(text), end + 2)]
    if prefix.endswith("${") or prefix.endswith("}."):
        return True
    if prefix.endswith("<") or prefix.endswith("`") or prefix.endswith("--"):
        return True
    if suffix.startswith(("`", "}", ">")):
        return True
    return False


def _prepare_text_for_bare_domains(text: str, *, source_path: str | None) -> str:
    if source_path is None:
        return text

    suffix = Path(source_path).suffix.lower()
    name = Path(source_path).name.lower()
    if suffix not in {".md", ".markdown", ".mdx", ".rst", ".txt"} and name != "skill.md":
        return text

    without_fences = _MARKDOWN_FENCE_RE.sub("\n", text)
    return _MARKDOWN_INLINE_CODE_RE.sub(" ", without_fences)


def _is_code_like_label(label: str) -> bool:
    lowered = label.lower()
    if lowered in _CODELIKE_SUFFIXES:
        return True
    if len(lowered) == 1:
        return True
    if any(char.isdigit() for char in lowered) and not lowered.isdigit():
        return True
    return any(
        lowered.startswith(prefix)
        for prefix in (
            "arg",
            "app",
            "agent",
            "client",
            "conn",
            "controller",
            "env",
            "event",
            "item",
            "param",
            "part",
            "path",
            "process",
            "prompt",
            "question",
            "response",
            "result",
            "sandbox",
            "sdk",
            "session",
            "state",
        )
    )


def _append_variant(variants: list[tuple[str, str]], kind: str, value: str) -> None:
    normalized = value.strip()
    if not normalized:
        return
    if any(existing == normalized for _, existing in variants):
        return
    variants.append((kind, normalized))


def _expand_once(text: str) -> list[tuple[str, str]]:
    expanded: list[tuple[str, str]] = []

    for decoded in extract_base64_segments(text):
        _append_variant(expanded, "decoded-base64", decoded)

    for decoded in extract_hex_segments(text):
        _append_variant(expanded, "decoded-hex", decoded)

    for decoded in extract_powershell_encoded_segments(text):
        _append_variant(expanded, "decoded-powershell", decoded)

    if _PERCENT_ESCAPE_RE.search(text):
        decoded = unquote(text)
        if decoded != text:
            _append_variant(expanded, "decoded-percent", decoded)

    if _UNICODE_ESCAPE_RE.search(text):
        try:
            decoded = codecs.decode(text, "unicode_escape")
        except Exception:
            decoded = text
        if decoded != text:
            _append_variant(expanded, "decoded-unicode", decoded)

    for decoded in _extract_charcode_segments(text):
        _append_variant(expanded, "decoded-charcode", decoded)

    for reconstructed in _extract_python_strings(text):
        _append_variant(expanded, "python-ast", reconstructed)

    for reconstructed in _extract_javascript_strings(text):
        _append_variant(expanded, "javascript-ast", reconstructed)

    for reconstructed in _extract_shell_strings(text):
        _append_variant(expanded, "shell-ast", reconstructed)

    return expanded


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
        self._env: dict[str, object] = {}
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
            if isinstance(value, str) and value:
                self.extracted.append(value)
        for keyword in node.keywords:
            value = self._eval(keyword.value)
            if isinstance(value, str) and value:
                self.extracted.append(value)
        self.generic_visit(node)

    def _eval(self, node: ast.AST) -> object | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self._env.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._eval(node.left)
            right = self._eval(node.right)
            if isinstance(left, str) and isinstance(right, str):
                return left + right
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            left = self._eval(node.left)
            right = self._eval(node.right)
            try:
                if isinstance(left, str):
                    if isinstance(right, tuple):
                        return left % right
                    if isinstance(right, str):
                        return left % right
            except Exception:
                return None
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue):
                    nested = self._eval(value.value)
                    if not isinstance(nested, str):
                        return None
                    parts.append(nested)
            return "".join(parts)
        if isinstance(node, ast.List | ast.Tuple):
            items: list[str] = []
            for element in node.elts:
                value = self._eval(element)
                if not isinstance(value, str):
                    return None
                items.append(value)
            return items if isinstance(node, ast.List) else tuple(items)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = self._eval(node.func.value)
            if node.func.attr == "format" and isinstance(target, str):
                args = [self._eval(argument) for argument in node.args]
                if any(not isinstance(argument, str) for argument in args):
                    return None
                kwargs = {}
                for keyword in node.keywords:
                    value = self._eval(keyword.value)
                    if not isinstance(value, str) or keyword.arg is None:
                        return None
                    kwargs[keyword.arg] = value
                try:
                    return target.format(*args, **kwargs)
                except Exception:
                    return None
            if node.func.attr == "join" and isinstance(target, str) and node.args:
                items = self._eval(node.args[0])
                if isinstance(items, list | tuple) and all(isinstance(item, str) for item in items):
                    return target.join(items)
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
    try:
        program = esprima.parseScript(text, tolerant=True)
    except Exception:
        return []

    collector = _JavaScriptStringCollector()
    collector.visit(program)
    return collector.extracted


class _JavaScriptStringCollector:
    def __init__(self) -> None:
        self._env: dict[str, object] = {}
        self.extracted: list[str] = []

    def visit(self, node) -> None:
        node_type = getattr(node, "type", None)
        if node_type == "Program":
            for statement in node.body:
                self.visit(statement)
            return
        if node_type == "VariableDeclaration":
            for declaration in node.declarations:
                self.visit(declaration)
            return
        if node_type == "VariableDeclarator":
            value = self._eval(node.init)
            if getattr(node.id, "type", None) == "Identifier" and value is not None:
                self._env[node.id.name] = value
                if isinstance(value, str):
                    self.extracted.append(value)
            return
        if node_type == "ExpressionStatement":
            self.visit(node.expression)
            return
        if node_type == "CallExpression":
            self._collect_call(node)
            for argument in node.arguments:
                self.visit(argument)
            return
        if node_type == "AssignmentExpression":
            value = self._eval(node.right)
            if getattr(node.left, "type", None) == "Identifier" and value is not None:
                self._env[node.left.name] = value
            return

    def _collect_call(self, node) -> None:
        callee_name = _js_callee_name(node.callee)
        if callee_name in {"fetch", "axios.get", "axios.post", "axios.put", "axios.delete"}:
            if node.arguments:
                value = self._eval(node.arguments[0])
                if isinstance(value, str):
                    self.extracted.append(value)
        if callee_name == "XMLHttpRequest.open" and len(node.arguments) >= 2:
            value = self._eval(node.arguments[1])
            if isinstance(value, str):
                self.extracted.append(value)

    def _eval(self, node) -> object | None:
        if node is None:
            return None
        node_type = getattr(node, "type", None)
        if node_type == "Literal":
            return node.value if isinstance(node.value, str | int | float) else None
        if node_type == "Identifier":
            return self._env.get(node.name)
        if node_type == "ArrayExpression":
            values: list[str] = []
            for element in node.elements:
                value = self._eval(element)
                if not isinstance(value, str):
                    return None
                values.append(value)
            return values
        if node_type == "TemplateLiteral":
            parts: list[str] = []
            for index, quasi in enumerate(node.quasis):
                parts.append(quasi.value.cooked or "")
                if index < len(node.expressions):
                    value = self._eval(node.expressions[index])
                    if not isinstance(value, str):
                        return None
                    parts.append(value)
            return "".join(parts)
        if node_type == "BinaryExpression" and node.operator == "+":
            left = self._eval(node.left)
            right = self._eval(node.right)
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            return None
        if node_type == "CallExpression":
            callee_name = _js_callee_name(node.callee)
            if callee_name == "atob" and node.arguments:
                token = self._eval(node.arguments[0])
                if isinstance(token, str):
                    try:
                        return base64.b64decode(token, validate=True).decode("utf-8")
                    except Exception:
                        return None
            if callee_name == "decodeURIComponent" and node.arguments:
                token = self._eval(node.arguments[0])
                if isinstance(token, str):
                    return unquote(token)
            if callee_name == "String.fromCharCode":
                values: list[int] = []
                for argument in node.arguments:
                    value = self._eval(argument)
                    if isinstance(value, (int, float)):
                        values.append(int(value))
                    else:
                        return None
                try:
                    return "".join(chr(value) for value in values)
                except ValueError:
                    return None
            if getattr(node.callee, "type", None) == "MemberExpression":
                property_name = _js_property_name(node.callee)
                if property_name == "join" and node.arguments:
                    target = self._eval(node.callee.object)
                    separator = self._eval(node.arguments[0])
                    if isinstance(target, list) and isinstance(separator, str):
                        return separator.join(target)
            return None
        return None


def _js_callee_name(node) -> str | None:
    node_type = getattr(node, "type", None)
    if node_type == "Identifier":
        return node.name
    if node_type == "MemberExpression":
        object_name = _js_callee_name(node.object)
        property_name = _js_property_name(node)
        if property_name is None:
            return object_name
        if object_name:
            return f"{object_name}.{property_name}"
        return property_name
    return None


def _js_property_name(node) -> str | None:
    prop = getattr(node, "property", None)
    if prop is None:
        return None
    if getattr(prop, "type", None) == "Identifier":
        return prop.name
    if getattr(prop, "type", None) == "Literal" and isinstance(prop.value, str):
        return prop.value
    return None


def _extract_shell_strings(text: str) -> list[str]:
    env: dict[str, str] = {}
    extracted: list[str] = []
    try:
        commands = bashlex.parse(text)
    except Exception:
        commands = []

    for command in commands:
        if command.kind != "command":
            continue
        words: list[str] = []
        for part in getattr(command, "parts", []) or []:
            if part.kind == "assignment":
                name, _, raw_value = part.word.partition("=")
                value = _strip_shell_quotes(_resolve_shell_expression(raw_value, env) or raw_value)
                env[name] = value
                extracted.append(value)
                continue
            if part.kind == "word":
                words.append(_resolve_shell_word(part, env))
        if words and words[0] in {"curl", "wget"}:
            for word in words[1:]:
                if word.startswith("http://") or word.startswith("https://"):
                    extracted.append(word)
    return extracted


def _resolve_shell_expression(expression: str, env: dict[str, str]) -> str | None:
    normalized = expression.replace("${", "$").replace("}", "")
    parts = re.split(r"(\$[A-Za-z_][A-Za-z0-9_]*)", normalized)
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
        return _strip_shell_quotes(expression)
    return "".join(resolved)


def _resolve_shell_word(node, env: dict[str, str]) -> str:
    value = getattr(node, "word", "")
    resolved = _resolve_shell_expression(value, env)
    if resolved is None:
        return _strip_shell_quotes(value)
    return _strip_shell_quotes(resolved)


def _strip_shell_quotes(value: str) -> str:
    stripped = value.strip()
    if (stripped.startswith('"') and stripped.endswith('"')) or (
        stripped.startswith("'") and stripped.endswith("'")
    ):
        return stripped[1:-1]
    return stripped
