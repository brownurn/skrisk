"""Minimal heuristic analyzer for agent skill content."""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
from pathlib import Path
import re
from urllib.parse import urlparse

from skrisk.analysis.language_extractors import expand_text_variants, extract_bare_domains

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
_SENSITIVE_SOURCE_PATTERNS = (
    re.compile(r"~\/\.ssh(?:\/|$)", re.IGNORECASE),
    re.compile(r"(?:^|[^\w])\.ssh\/", re.IGNORECASE),
    re.compile(r"(?:^|[^\w])id_rsa(?:$|[^\w])", re.IGNORECASE),
    re.compile(r"~\/\.aws\/credentials\b", re.IGNORECASE),
    re.compile(r"aws_secret_access_key", re.IGNORECASE),
    re.compile(r"aws_access_key_id", re.IGNORECASE),
    re.compile(r"aws_session_token", re.IGNORECASE),
    re.compile(r"(?:^|[^\w])api[_-]?key(?:$|[^\w])", re.IGNORECASE),
    re.compile(r"(?:^|[^\w])secret(?:$|[^\w])", re.IGNORECASE),
    re.compile(r"(?:^|[^\w])token(?:$|[^\w])", re.IGNORECASE),
    re.compile(r"(?:^|[^\w])cookie(?:$|[^\w])", re.IGNORECASE),
    re.compile(r"(?:^|[^\w])authorization(?:$|[^\w])", re.IGNORECASE),
    re.compile(
        r"\b(?:cat|type)\b[^\n]*\b\.env(?:\.[A-Za-z0-9._-]+)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:open|read_text|read_bytes|readfile|readfilesync|slurp)\b[^\n]*\b\.env(?:\.[A-Za-z0-9._-]+)?\b",
        re.IGNORECASE,
    ),
    re.compile(r"@\.env(?:\.[A-Za-z0-9._-]+)?\b", re.IGNORECASE),
)
_REMOTE_SINK_PATTERNS = (
    re.compile(
        r"\bcurl\b[^\n]*https?://[^\s\"')>]+[^\n]*(?:\b(?:post|put|upload)\b|-f\b|--form\b|-d\b|--data\b|--upload-file\b|-t\b)",
        re.IGNORECASE,
    ),
    re.compile(r"\brequests\.(?:post|put)\s*\(", re.IGNORECASE),
    re.compile(r"\bhttpx\.(?:post|put)\s*\(", re.IGNORECASE),
    re.compile(r"\baxios\.(?:post|put)\s*\(", re.IGNORECASE),
    re.compile(r"\bfetch\s*\(", re.IGNORECASE),
    re.compile(r"https?://[^\s\"')>]+[^\n]*\b(?:upload|webhook|collect|submit|exfil)\b", re.IGNORECASE),
)
_OBFUSCATING_VARIANTS = {
    "decoded-base64",
    "decoded-hex",
    "decoded-powershell",
    "decoded-charcode",
}
_DECODED_BARE_DOMAIN_VARIANTS = {
    "decoded-base64",
    "decoded-hex",
    "decoded-powershell",
    "decoded-charcode",
}
_TEXTLIKE_BARE_DOMAIN_FILES = {".json", ".md", ".rst", ".txt", ".yaml", ".yml"}


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
            variants = expand_text_variants(original_text)
            expanded = "\n".join(text for _, text in variants)
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

            if any(variant_kind in _OBFUSCATING_VARIANTS for variant_kind, _ in variants[1:]):
                findings.append(
                    Finding(
                        path=path,
                        category="obfuscation",
                        severity="high",
                        evidence="Decoded or reconstructed payload surfaced during analysis",
                    )
                )

            exfil_evidence = _detect_data_exfiltration_evidence(expanded)
            if exfil_evidence is not None:
                findings.append(
                    Finding(
                        path=path,
                        category="data_exfiltration",
                        severity="critical",
                        evidence=exfil_evidence,
                    )
                )

            for variant_kind, variant_text in variants:
                for match in _URL_RE.finditer(variant_text):
                    url = _normalize_url_token(match.group(0))
                    if not url:
                        continue
                    indicators.append(
                        ExtractedIndicator(
                            path=path,
                            indicator_type="url",
                            indicator_value=url,
                            extraction_kind=_url_extraction_kind(variant_kind),
                            raw_value=match.group(0),
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

                if not _should_extract_bare_domains(path=path, variant_kind=variant_kind):
                    continue

                for domain in extract_bare_domains(variant_text):
                    domains.add(domain)
                    indicators.append(
                        ExtractedIndicator(
                            path=path,
                            indicator_type=_host_indicator_type(domain),
                            indicator_value=domain,
                            extraction_kind=_domain_extraction_kind(variant_kind),
                            raw_value=domain,
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


def _url_extraction_kind(variant_kind: str) -> str:
    if variant_kind == "original":
        return "inline-url"
    return f"{variant_kind}-url"


def _domain_extraction_kind(variant_kind: str) -> str:
    if variant_kind == "original":
        return "bare-domain"
    return f"{variant_kind}-domain"


def _should_extract_bare_domains(*, path: str, variant_kind: str) -> bool:
    if variant_kind in _DECODED_BARE_DOMAIN_VARIANTS:
        return True
    if variant_kind != "original":
        return False
    path_obj = Path(path)
    if path_obj.name.upper() == "SKILL.MD":
        return True
    return path_obj.suffix.lower() in _TEXTLIKE_BARE_DOMAIN_FILES


def _detect_data_exfiltration_evidence(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    for index, line in enumerate(lines):
        window_lines = lines[max(0, index - 1) : min(len(lines), index + 2)]
        window_text = "\n".join(window_lines)
        if not _contains_sensitive_source(window_text):
            continue
        if not _contains_remote_sink(window_text):
            continue
        for candidate in window_lines:
            if _contains_remote_sink(candidate):
                return candidate
        return window_text

    return None


def _contains_sensitive_source(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SENSITIVE_SOURCE_PATTERNS)


def _contains_remote_sink(text: str) -> bool:
    lowered = text.lower()
    if "http://" not in lowered and "https://" not in lowered and "webhook" not in lowered:
        return False

    if any(pattern.search(text) for pattern in _REMOTE_SINK_PATTERNS):
        return True

    return any(marker in lowered for marker in (" upload ", " post ", " put ", " send "))


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
