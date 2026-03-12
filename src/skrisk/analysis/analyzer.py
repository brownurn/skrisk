"""Minimal heuristic analyzer for agent skill content."""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from skrisk.analysis.language_extractors import (
    expand_text_variants,
    extract_bare_domains,
    is_meaningful_domain_candidate,
)

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
_LOW_SIGNAL_DOMAINS = {
    "localhost",
}
_RESERVED_DOMAIN_SUFFIXES = {
    "example.com",
    "example.net",
    "example.org",
}
_MAX_URL_INDICATOR_LENGTH = 1800
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1F\x7F]")
_PERCENT_ENCODED_CONTROL_RE = re.compile(r"%(?:00|0a|0d|09)", re.IGNORECASE)
_UNICODE_DOT_SEPARATORS = ("\u3002", "\uff0e", "\uff61")
_INVALID_NETLOC_MARKERS = ("${", "$(", "`", "<", ">", "{", "}", "[", "]")


@dataclass(slots=True)
class Finding:
    path: str
    category: str
    severity: str
    evidence: str
    context: str = "direct_operational"
    details: dict[str, Any] | None = None


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

            outbound_evidence = _detect_outbound_evidence(expanded)
            if outbound_evidence is not None:
                findings.append(
                    Finding(
                        path=path,
                        category=outbound_evidence["category"],
                        severity=_finding_severity(outbound_evidence["category"], file_context),
                        evidence=str(outbound_evidence["evidence"]),
                        context=file_context,
                        details=outbound_evidence["details"],
                    )
                )

            for variant_kind, variant_text in variants:
                for match in _URL_RE.finditer(variant_text):
                    url = _normalize_url_token(match.group(0))
                    if not _should_record_url_indicator(url):
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
                        indicator_type = _host_indicator_type(normalized_hostname)
                        if _should_record_host_indicator(
                            normalized_hostname,
                            indicator_type=indicator_type,
                        ):
                            if indicator_type == "domain":
                                domains.add(normalized_hostname)
                            indicators.append(
                                ExtractedIndicator(
                                    path=path,
                                    indicator_type=indicator_type,
                                    indicator_value=normalized_hostname,
                                    extraction_kind="url-host",
                                    raw_value=url,
                                )
                            )

                if not _should_extract_bare_domains(path=path, variant_kind=variant_kind):
                    continue

                for domain in extract_bare_domains(variant_text, source_path=path):
                    if not _should_record_host_indicator(domain, indicator_type="domain"):
                        continue
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
                    "details": finding.details,
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


def _should_record_url_indicator(value: str) -> bool:
    if not value:
        return False
    # Badge/image URLs often embed massive inline assets in query params and
    # are not useful IOCs; keep them out of the indicator corpus entirely.
    if len(value) > _MAX_URL_INDICATOR_LENGTH:
        return False
    if _CONTROL_CHAR_RE.search(value):
        return False
    if _PERCENT_ENCODED_CONTROL_RE.search(value):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        return False
    if any(marker in parsed.netloc for marker in _INVALID_NETLOC_MARKERS):
        return False
    if any(separator in parsed.hostname for separator in _UNICODE_DOT_SEPARATORS):
        return False
    return True


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
    if category == "credential_transmission" and context == "reference_example":
        return "medium"
    if category == "prompt_injection" and context == "reference_example":
        return "medium"
    if category == "obfuscation":
        return "medium"
    if category == "credential_transmission":
        return "high"
    if category in _HIGH_RISK_CATEGORIES:
        return "critical"
    return "high"


def _detect_outbound_evidence(text: str) -> dict[str, Any] | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    for index, line in enumerate(lines):
        window_lines = lines[max(0, index - 1) : min(len(lines), index + 2)]
        window_text = "\n".join(window_lines)
        sink = _extract_remote_sink(window_text)
        if sink is None:
            continue
        details = _extract_outbound_details(window_text, sink)
        if details is None:
            continue
        evidence = next((candidate for candidate in window_lines if sink["sink_url"] in candidate), line)
        return {
            "category": "data_exfiltration"
            if details["kind"] == "secret_exfiltration"
            else "credential_transmission",
            "evidence": evidence,
            "details": details,
        }

    return None


_SHELL_ENV_CAPTURE_RE = re.compile(r"\$([A-Z][A-Z0-9_]{2,})|\$\{([A-Z][A-Z0-9_]{2,})\}")
_PROCESS_ENV_CAPTURE_RE = re.compile(
    r"(?:process\.env\.([A-Z][A-Z0-9_]{2,})|os\.environ\[[\"']([A-Z][A-Z0-9_]{2,})[\"']\]|os\.getenv\([\"']([A-Z][A-Z0-9_]{2,})[\"']\))"
)
_AUTH_HEADER_CAPTURE_RE = re.compile(
    r"authorization[^\\n]*bearer\s+(?:\$([A-Z][A-Z0-9_]{2,})|\$\{([A-Z][A-Z0-9_]{2,})\}|process\.env\.([A-Z][A-Z0-9_]{2,})|os\.environ\[[\"']([A-Z][A-Z0-9_]{2,})[\"']\]|os\.getenv\([\"']([A-Z][A-Z0-9_]{2,})[\"']\))",
    re.IGNORECASE,
)
_SECRET_PATH_CAPTURE_PATTERNS = (
    re.compile(r"~\/\.ssh(?:\/[A-Za-z0-9._-]+)?", re.IGNORECASE),
    re.compile(r"~\/\.aws\/credentials\b", re.IGNORECASE),
    re.compile(r"(?:^|[^\w])id_rsa(?:$|[^\w])", re.IGNORECASE),
    re.compile(r"\.env(?:\.[A-Za-z0-9._-]+)?\b", re.IGNORECASE),
)
_EXPLICIT_SECRET_VARS = {
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SESSION_TOKEN",
}


def _extract_remote_sink(text: str) -> dict[str, str] | None:
    lowered = text.lower()
    if "http://" not in lowered and "https://" not in lowered and "webhook" not in lowered:
        return None
    if not any(pattern.search(text) for pattern in _REMOTE_SINK_PATTERNS) and not any(
        marker in lowered
        for marker in (
            "fetch(",
            "requests.post",
            "requests.put",
            "httpx.post",
            "httpx.put",
            "axios.post",
            "axios.put",
        )
    ):
        return None

    sink_url_match = _URL_RE.search(text)
    sink_url = _normalize_url_token(sink_url_match.group(0)) if sink_url_match else None
    if not sink_url or not _should_record_url_indicator(sink_url):
        return None

    try:
        sink_host = urlparse(sink_url).hostname or ""
    except ValueError:
        return None

    if not sink_host:
        return None

    if "curl" in lowered:
        sink_kind = "curl"
    elif "requests.post" in lowered or "requests.put" in lowered:
        sink_kind = "requests.post"
    elif "httpx.post" in lowered or "httpx.put" in lowered:
        sink_kind = "httpx.post"
    elif "axios.post" in lowered or "axios.put" in lowered:
        sink_kind = "axios.post"
    elif "fetch(" in lowered:
        sink_kind = "fetch"
    else:
        sink_kind = "remote_sink"

    return {
        "sink_kind": sink_kind,
        "sink_url": sink_url,
        "sink_host": sink_host.lower(),
    }


def _extract_outbound_details(
    text: str,
    sink: dict[str, str],
) -> dict[str, Any] | None:
    source_values = _extract_source_values(text)
    if not source_values:
        return None

    auth_values = _extract_auth_header_values(text)
    if auth_values:
        return {
            "kind": "credential_transmission",
            "source_kind": "authorization_header",
            "source_values": auth_values,
            "sink_kind": sink["sink_kind"],
            "sink_url": sink["sink_url"],
            "sink_host": sink["sink_host"],
            "transport_detail": "Authorization header",
        }

    transport_detail = "request body"
    lowered = text.lower()
    if "-f " in lowered or "--form" in lowered:
        transport_detail = "multipart form upload"
    elif "-d " in lowered or "--data" in lowered or "json=" in lowered or "body:" in lowered:
        transport_detail = "request body"

    source_kind = "env_var"
    if any(value.startswith("~/.") or value.startswith(".env") or value == "id_rsa" for value in source_values):
        source_kind = "secret_path"

    return {
        "kind": "secret_exfiltration",
        "source_kind": source_kind,
        "source_values": source_values,
        "sink_kind": sink["sink_kind"],
        "sink_url": sink["sink_url"],
        "sink_host": sink["sink_host"],
        "transport_detail": transport_detail,
    }


def _extract_source_values(text: str) -> list[str]:
    values: list[str] = []

    for match in _AUTH_HEADER_CAPTURE_RE.finditer(text):
        values.extend(value for value in match.groups() if value)

    for match in _SHELL_ENV_CAPTURE_RE.finditer(text):
        values.extend(value for value in match.groups() if value)

    for match in _PROCESS_ENV_CAPTURE_RE.finditer(text):
        values.extend(value for value in match.groups() if value)

    for pattern in _SECRET_PATH_CAPTURE_PATTERNS:
        values.extend(token.strip(" '\"") for token in pattern.findall(text))

    explicit = [value for value in values if value.upper() in _EXPLICIT_SECRET_VARS]
    if explicit:
        return _dedupe_values(explicit)

    if any(token in text.lower() for token in ("authorization", "cookie")):
        auth_like = [value for value in values if any(part in value.upper() for part in ("KEY", "TOKEN", "SECRET", "COOKIE", "AUTH"))]
        if auth_like:
            return _dedupe_values(auth_like)

    secretish = [
        value
        for value in values
        if value.startswith("~/.")
        or value.startswith(".env")
        or value == "id_rsa"
        or any(part in value.upper() for part in ("KEY", "TOKEN", "SECRET", "COOKIE", "AUTH"))
    ]
    return _dedupe_values(secretish)


def _extract_auth_header_values(text: str) -> list[str]:
    values: list[str] = []
    for match in _AUTH_HEADER_CAPTURE_RE.finditer(text):
        values.extend(value for value in match.groups() if value)
    return _dedupe_values(values)


def _dedupe_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


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
        ("credential_transmission", "direct_operational"): 18,
        ("credential_transmission", "reference_example"): 5,
        ("prompt_injection", "direct_operational"): 15,
        ("prompt_injection", "reference_example"): 5,
        ("obfuscation", "direct_operational"): 8,
        ("obfuscation", "reference_example"): 5,
    }
    group_caps = {
        ("remote_code_execution", "reference_example"): 5,
        ("data_exfiltration", "reference_example"): 15,
        ("credential_transmission", "reference_example"): 8,
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


def _should_record_host_indicator(value: str, *, indicator_type: str) -> bool:
    lowered = value.lower()
    if indicator_type == "domain":
        if lowered in _LOW_SIGNAL_DOMAINS or lowered.endswith(".localhost"):
            return False
        if any(lowered == suffix or lowered.endswith(f".{suffix}") for suffix in _RESERVED_DOMAIN_SUFFIXES):
            return False
        return is_meaningful_domain_candidate(lowered)

    try:
        ip_value = ipaddress.ip_address(lowered)
    except ValueError:
        return False

    return not (
        ip_value.is_private
        or ip_value.is_loopback
        or ip_value.is_link_local
        or ip_value.is_multicast
        or ip_value.is_reserved
        or ip_value.is_unspecified
    )


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
