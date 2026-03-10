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
_REFERENCE_PATH_MARKERS = (
    "references/",
    "reference/",
    "docs/",
    "doc/",
    "examples/",
    "example/",
)
_REFERENCE_FILE_NAMES = {
    "readme",
    "readme.md",
    "api.md",
    "configuration.md",
    "patterns.md",
    "installation.md",
    "troubleshooting.md",
    "quickstart.md",
}
_ROUTER_CATALOG_MARKERS = (
    "navigation guide only",
    "navigation guide",
    "available skills",
    "choose the relevant skill",
    "choose the relevant reference",
    "load the relevant reference",
    "load reference files",
    "catalog of skills",
    "catalog skill",
    "router skill",
    "index of skills",
)
_HIGH_RISK_CATEGORIES = {"remote_code_execution", "data_exfiltration"}
_SHARED_PLATFORM_DOMAINS = {
    "github.com",
    "gist.github.com",
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
    "storage.googleapis.com",
    "drive.google.com",
    "dropbox.com",
    "discord.com",
    "cdn.discordapp.com",
}


@dataclass(slots=True)
class Finding:
    path: str
    category: str
    severity: str
    evidence: str
    context: str = "direct_operational"


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
        router_catalog_skill = _is_router_catalog_skill(skill_slug=skill_slug, files=files)

        for path, original_text in files.items():
            file_context = _classify_file_context(path)
            variants = expand_text_variants(original_text)
            expanded = "\n".join(text for _, text in variants)
            expanded_lowered = expanded.lower()

            for marker in _PROMPT_PATTERNS:
                if marker in expanded_lowered:
                    findings.append(
                        Finding(
                            path=path,
                            category="prompt_injection",
                            severity=_finding_severity("prompt_injection", file_context),
                            evidence=marker,
                            context=file_context,
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
                            severity=_finding_severity("remote_code_execution", file_context),
                            evidence=match.group(0).strip(),
                            context=file_context,
                        )
                    )
                    break

            if any(variant_kind in _OBFUSCATING_VARIANTS for variant_kind, _ in variants[1:]):
                findings.append(
                    Finding(
                        path=path,
                        category="obfuscation",
                        severity=_finding_severity("obfuscation", file_context),
                        evidence="Decoded or reconstructed payload surfaced during analysis",
                        context=file_context,
                    )
                )

            exfil_evidence = _detect_data_exfiltration_evidence(expanded)
            if exfil_evidence is not None:
                findings.append(
                    Finding(
                        path=path,
                        category="data_exfiltration",
                        severity=_finding_severity("data_exfiltration", file_context),
                        evidence=exfil_evidence,
                        context=file_context,
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
        behavior_score = _behavior_score(findings, router_catalog_skill=router_catalog_skill)
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
                    "context": finding.context,
                }
                for finding in report.findings
            ],
        }


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    deduped: list[Finding] = []
    seen: set[tuple[str, str, str, str]] = set()

    for finding in findings:
        key = (finding.path, finding.category, finding.evidence, finding.context)
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


def _classify_file_context(path: str) -> str:
    normalized = path.replace("\\", "/").lower()
    name = Path(normalized).name.lower()

    if any(marker in normalized for marker in _REFERENCE_PATH_MARKERS):
        return "reference_example"
    if name in _REFERENCE_FILE_NAMES:
        return "reference_example"
    return "direct_operational"


def _is_router_catalog_skill(*, skill_slug: str, files: dict[str, str]) -> bool:
    lowered_slug = skill_slug.lower()
    if "catalog" in lowered_slug or "router" in lowered_slug:
        return True

    skill_markdown = files.get("SKILL.md") or files.get("skill.md") or ""
    lowered = skill_markdown.lower()
    return any(marker in lowered for marker in _ROUTER_CATALOG_MARKERS)


def _finding_severity(category: str, context: str) -> str:
    if category in _HIGH_RISK_CATEGORIES and context == "reference_example":
        return "medium"
    if category == "prompt_injection" and context == "reference_example":
        return "medium"
    if category == "obfuscation":
        return "medium"
    if category in _HIGH_RISK_CATEGORIES:
        return "critical"
    return "high"


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


def _behavior_score(findings: list[Finding], *, router_catalog_skill: bool) -> int:
    weights = {
        ("remote_code_execution", "direct_operational"): 35,
        ("remote_code_execution", "reference_example"): 5,
        ("data_exfiltration", "direct_operational"): 55,
        ("data_exfiltration", "reference_example"): 10,
        ("prompt_injection", "direct_operational"): 15,
        ("prompt_injection", "reference_example"): 5,
        ("obfuscation", "direct_operational"): 8,
        ("obfuscation", "reference_example"): 5,
    }
    group_caps = {
        ("remote_code_execution", "reference_example"): 5,
        ("data_exfiltration", "reference_example"): 15,
        ("prompt_injection", "reference_example"): 5,
        ("obfuscation", "reference_example"): 8,
        ("obfuscation", "direct_operational"): 12,
    }

    group_scores: dict[tuple[str, str], int] = {}
    for finding in findings:
        key = (finding.category, finding.context)
        weight = weights.get(key, 10)
        next_score = group_scores.get(key, 0) + weight
        group_scores[key] = min(next_score, group_caps.get(key, 100))

    total = sum(group_scores.values())
    if router_catalog_skill and not _has_direct_high_risk_finding(findings):
        total = min(total, 35)
    return min(100, total)


def _has_direct_high_risk_finding(findings: list[Finding]) -> bool:
    return any(
        finding.category in _HIGH_RISK_CATEGORIES and finding.context == "direct_operational"
        for finding in findings
    )


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
    if indicator_matches and severity == "critical" and behavior_score >= 35:
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
    indicator = match.get("indicator", {})
    indicator_type = (indicator.get("indicator_type") or "").lower()
    indicator_value = (indicator.get("normalized_value") or indicator.get("indicator_value") or "").lower()
    return any(
        _is_positive_observation(
            observation,
            indicator_type=indicator_type,
            indicator_value=indicator_value,
        )
        for observation in match.get("observations", [])
    )


def _is_positive_observation(
    observation: dict,
    *,
    indicator_type: str = "",
    indicator_value: str = "",
) -> bool:
    classification = (observation.get("classification") or "").lower()
    confidence = (observation.get("confidence_label") or "").lower()
    summary = (observation.get("summary") or "").lower()
    source_provider = (observation.get("source_provider") or "").lower()
    source_feed = (observation.get("source_feed") or "").lower()
    combined = " ".join(part for part in (classification, summary) if part)

    if (
        indicator_type == "domain"
        and indicator_value in _SHARED_PLATFORM_DOMAINS
        and source_provider == "abusech"
        and source_feed.startswith("urlhaus")
    ):
        return False

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
