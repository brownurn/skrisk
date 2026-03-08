"""Minimal heuristic analyzer for agent skill content."""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
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
class ExtractedIndicator:
    path: str
    indicator_type: str
    indicator_value: str
    extraction_kind: str
    raw_value: str


@dataclass(slots=True)
class RiskReport:
    publisher: str
    repo: str
    skill_slug: str
    severity: str
    score: int
    behavior_score: int
    findings: list[Finding] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    indicators: list[ExtractedIndicator] = field(default_factory=list)


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
        indicators: list[ExtractedIndicator] = []

        for path, original_text in files.items():
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
                url = _normalize_url_token(match.group(0))
                if not url:
                    continue
                indicators.append(
                    ExtractedIndicator(
                        path=path,
                        indicator_type="url",
                        indicator_value=url,
                        extraction_kind="inline-url",
                        raw_value=url,
                    )
                )
                try:
                    hostname = urlparse(url).hostname
                except ValueError:
                    continue
                if hostname:
                    normalized_hostname = hostname.lower()
                    domains.add(normalized_hostname)
                    indicators.append(
                        ExtractedIndicator(
                            path=path,
                            indicator_type=_host_indicator_type(normalized_hostname),
                            indicator_value=normalized_hostname,
                            extraction_kind="url-host",
                            raw_value=url,
                        )
                    )

        findings = _dedupe_findings(findings)
        indicators = _dedupe_indicators(indicators)
        behavior_score = _behavior_score(findings)
        severity = _severity_from_score(behavior_score)
        score = behavior_score

        return RiskReport(
            publisher=publisher,
            repo=repo,
            skill_slug=skill_slug,
            severity=severity,
            score=score,
            behavior_score=behavior_score,
            findings=findings,
            domains=sorted(domains),
            indicators=indicators,
        )

    def build_risk_report(
        self,
        *,
        report: RiskReport,
        indicator_matches: list[dict],
        change_score: int = 0,
    ) -> dict[str, object]:
        positive_matches = [match for match in indicator_matches if _is_positive_indicator_match(match)]
        intel_score = _intel_score(positive_matches)
        total_score = min(100, report.behavior_score + intel_score + change_score)
        severity = _severity_from_score(total_score)
        confidence = _confidence_label(
            behavior_score=report.behavior_score,
            indicator_matches=positive_matches,
            severity=severity,
        )
        return {
            "severity": severity,
            "score": total_score,
            "behavior_score": report.behavior_score,
            "intel_score": intel_score,
            "change_score": change_score,
            "confidence": confidence,
            "categories": [finding.category for finding in report.findings],
            "domains": report.domains,
            "indicator_matches": [
                {
                    **match.get("indicator", {}),
                    "observations": match.get("observations", []),
                }
                for match in indicator_matches
            ],
            "findings": [
                {
                    "path": finding.path,
                    "category": finding.category,
                    "severity": finding.severity,
                    "evidence": finding.evidence,
                }
                for finding in report.findings
            ],
        }


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


def _normalize_url_token(raw_value: str) -> str:
    value = raw_value.strip()
    if "](" in value:
        value = value.split("](", 1)[0]
    return value.rstrip("],.;:")


def _dedupe_indicators(indicators: list[ExtractedIndicator]) -> list[ExtractedIndicator]:
    deduped: list[ExtractedIndicator] = []
    seen: set[tuple[str, str, str, str]] = set()

    for indicator in indicators:
        key = (
            indicator.path,
            indicator.indicator_type,
            indicator.indicator_value,
            indicator.extraction_kind,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(indicator)

    return deduped


def _behavior_score(findings: list[Finding]) -> int:
    weights = {
        "remote_code_execution": 50,
        "data_exfiltration": 55,
        "prompt_injection": 15,
        "obfuscation": 20,
    }
    return min(100, sum(weights.get(finding.category, 10) for finding in findings))


def _intel_score(indicator_matches: list[dict]) -> int:
    score = 0
    for match in indicator_matches:
        observations = match.get("observations", [])
        if any((observation.get("confidence_label") or "").lower() == "high" for observation in observations):
            score += 20
        elif observations:
            score += 10
    return min(40, score)


def _severity_from_score(score: int) -> str:
    if score >= 45:
        return "critical"
    if score >= 25:
        return "high"
    if score >= 10:
        return "medium"
    return "none"


def _confidence_label(
    *,
    behavior_score: int,
    indicator_matches: list[dict],
    severity: str,
) -> str:
    if indicator_matches and severity == "critical" and behavior_score >= 40:
        return "confirmed"
    if indicator_matches or behavior_score >= 25:
        return "likely"
    return "suspected"


def _host_indicator_type(value: str) -> str:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return "domain"
    return "ip"


def _is_positive_indicator_match(match: dict) -> bool:
    return any(_is_positive_observation(observation) for observation in match.get("observations", []))


def _is_positive_observation(observation: dict) -> bool:
    classification = (observation.get("classification") or "").lower()
    confidence = (observation.get("confidence_label") or "").lower()
    summary = (observation.get("summary") or "").lower()
    combined = " ".join(part for part in (classification, summary) if part)

    if any(
        marker in combined
        for marker in (
            "benign",
            "harmless",
            "false positive",
            "informational",
        )
    ):
        return False

    if any(
        marker in combined
        for marker in (
            "malicious",
            "malware",
            "payload",
            "stealer",
            "trojan",
            "botnet",
            "phish",
            "exploit",
            "ransom",
            "c2",
            "download",
            "loader",
        )
    ):
        return True

    return confidence == "high"
