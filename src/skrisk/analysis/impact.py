"""Install impact and priority scoring helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ImpactMetrics:
    """Derived install telemetry used for prioritization."""

    current_weekly_installs: int | None
    previous_weekly_installs: int | None
    peak_weekly_installs: int | None
    install_delta: int | None
    impact_score: int
    priority_score: int


def bucket_weekly_installs(weekly_installs: int | None) -> int:
    """Map a weekly install count onto the approved impact ladder."""

    if weekly_installs is None or weekly_installs <= 0:
        return 0
    if weekly_installs < 10:
        return 5
    if weekly_installs < 100:
        return 15
    if weekly_installs < 1_000:
        return 30
    if weekly_installs < 10_000:
        return 50
    if weekly_installs < 50_000:
        return 70
    return 90


def compute_install_delta(
    current_weekly_installs: int | None,
    previous_weekly_installs: int | None,
) -> int | None:
    """Return the observed install delta when both values are known."""

    if current_weekly_installs is None or previous_weekly_installs is None:
        return None
    return current_weekly_installs - previous_weekly_installs


def compute_impact_score(
    *,
    current_weekly_installs: int | None,
    previous_weekly_installs: int | None = None,
) -> int:
    """Compute install-derived impact from reach and momentum."""

    base_score = bucket_weekly_installs(current_weekly_installs)
    if current_weekly_installs is None or previous_weekly_installs is None:
        return base_score
    if previous_weekly_installs <= 0:
        return min(100, base_score + 20 if current_weekly_installs > 0 else base_score)

    ratio = current_weekly_installs / previous_weekly_installs
    momentum_adjustment = 0
    if ratio >= 2:
        momentum_adjustment = 20
    elif ratio >= 1.1:
        momentum_adjustment = 10
    elif ratio <= 0.5:
        momentum_adjustment = -10

    return max(0, min(100, base_score + momentum_adjustment))


def compute_priority_score(
    *,
    risk_score: int,
    severity: str,
    confidence: str | None,
    impact_score: int,
) -> int:
    """Combine risk, confidence, severity, and impact into a triage score."""

    severity_multiplier = {
        "none": 0.5,
        "low": 0.7,
        "medium": 0.9,
        "high": 1.0,
        "critical": 1.1,
    }.get(severity, 1.0)
    confidence_multiplier = {
        "suspected": 0.9,
        "likely": 1.0,
        "confirmed": 1.1,
    }.get(confidence or "", 1.0)
    impact_multiplier = 1 + (impact_score / 200)
    priority = risk_score * severity_multiplier * confidence_multiplier * impact_multiplier
    return max(0, min(100, round(priority)))


def compute_priority_metrics(
    *,
    risk_score: int,
    severity: str,
    confidence: str | None,
    current_weekly_installs: int | None,
    previous_weekly_installs: int | None = None,
    peak_weekly_installs: int | None = None,
) -> ImpactMetrics:
    """Return the combined impact and priority metrics for a skill."""

    impact_score = compute_impact_score(
        current_weekly_installs=current_weekly_installs,
        previous_weekly_installs=previous_weekly_installs,
    )
    return ImpactMetrics(
        current_weekly_installs=current_weekly_installs,
        previous_weekly_installs=previous_weekly_installs,
        peak_weekly_installs=peak_weekly_installs,
        install_delta=compute_install_delta(
            current_weekly_installs=current_weekly_installs,
            previous_weekly_installs=previous_weekly_installs,
        ),
        impact_score=impact_score,
        priority_score=compute_priority_score(
            risk_score=risk_score,
            severity=severity,
            confidence=confidence,
            impact_score=impact_score,
        ),
    )
