"""Minimal heuristic analyzer for agent skill content."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from urllib.parse import urlparse

from skrisk.analysis.deobfuscator import decode_base64_segments

_URL_RE = re.compile(r"https?://[^\s\"')>]+", re.IGNORECASE)
_PROMPT_PATTERNS = (
    "ignore previous instructions",
    "follow this skill exactly",
)
_REMOTE_EXEC_PATTERNS = (
    re.compile(r"\bcurl\b[^\n|]+\|\s*(?:sh|bash)\b", re.IGNORECASE),
    re.compile(r"\bwget\b[^\n|]+\|\s*(?:sh|bash)\b", re.IGNORECASE),
    re.compile(r"\bbase64\s+-d\b[^\n|]*\|\s*(?:sh|bash)\b", re.IGNORECASE),
    re.compile(r"\bpowershell\b[^\n]*-enc\b", re.IGNORECASE),
)
_EXFIL_PATTERNS = (
    "~/.ssh",
    "~/.aws/credentials",
    "aws_secret_access_key",
    "id_rsa",
    ".env",
)


@dataclass(slots=True)
class Finding:
    path: str
    category: str
    severity: str
    evidence: str


@dataclass(slots=True)
class RiskReport:
    publisher: str
    repo: str
    skill_slug: str
    severity: str
    score: int
    findings: list[Finding] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)


class SkillAnalyzer:
    """Best-effort static analysis for skill content."""

    def analyze_skill(
        self,
        *,
        publisher: str,
        repo: str,
        skill_slug: str,
        files: dict[str, str],
    ) -> RiskReport:
        findings: list[Finding] = []
        domains: set[str] = set()

        for path, original_text in files.items():
            lowered = original_text.lower()
            expanded = decode_base64_segments(original_text)
            expanded_lowered = expanded.lower()

            for marker in _PROMPT_PATTERNS:
                if marker in expanded_lowered:
                    findings.append(
                        Finding(
                            path=path,
                            category="prompt_injection",
                            severity="high",
                            evidence=marker,
                        )
                    )
                    break

            for pattern in _REMOTE_EXEC_PATTERNS:
                match = pattern.search(expanded)
                if match:
                    findings.append(
                        Finding(
                            path=path,
                            category="remote_code_execution",
                            severity="critical",
                            evidence=match.group(0).strip(),
                        )
                    )
                    break

            if expanded != original_text:
                findings.append(
                    Finding(
                        path=path,
                        category="obfuscation",
                        severity="high",
                        evidence="Base64-decoded payload surfaced during analysis",
                    )
                )

            if any(indicator in expanded_lowered for indicator in _EXFIL_PATTERNS):
                post_lines = [
                    line.strip()
                    for line in expanded.splitlines()
                    if "http" in line.lower()
                    and any(indicator in line.lower() for indicator in _EXFIL_PATTERNS)
                ]
                if "upload" in expanded_lowered or "post" in expanded_lowered or post_lines:
                    findings.append(
                        Finding(
                            path=path,
                            category="data_exfiltration",
                            severity="critical",
                            evidence=post_lines[0] if post_lines else "Sensitive paths or secrets sent to remote endpoint",
                        )
                    )

            for match in _URL_RE.finditer(expanded):
                hostname = urlparse(match.group(0)).hostname
                if hostname:
                    domains.add(hostname.lower())

        findings = _dedupe_findings(findings)
        severity = _score_findings(findings)
        score = _score_value(severity, findings)

        return RiskReport(
            publisher=publisher,
            repo=repo,
            skill_slug=skill_slug,
            severity=severity,
            score=score,
            findings=findings,
            domains=sorted(domains),
        )


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    deduped: list[Finding] = []
    seen: set[tuple[str, str, str]] = set()

    for finding in findings:
        key = (finding.path, finding.category, finding.evidence)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)

    return deduped


def _score_findings(findings: list[Finding]) -> str:
    if not findings:
        return "none"

    categories = {finding.category for finding in findings}
    if {"remote_code_execution", "data_exfiltration"} & categories:
        return "critical"
    if {"prompt_injection", "obfuscation"} & categories:
        return "high"
    return "medium"


def _score_value(severity: str, findings: list[Finding]) -> int:
    if severity == "critical":
        return min(100, 80 + len(findings) * 5)
    if severity == "high":
        return min(79, 55 + len(findings) * 5)
    if severity == "medium":
        return min(54, 30 + len(findings) * 5)
    return 0
