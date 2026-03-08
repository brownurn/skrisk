from __future__ import annotations

from skrisk.analysis.impact import (
    ImpactMetrics,
    bucket_weekly_installs,
    compute_impact_score,
    compute_priority_metrics,
)


def test_bucket_weekly_installs_maps_to_approved_ladder() -> None:
    assert bucket_weekly_installs(None) == 0
    assert bucket_weekly_installs(0) == 0
    assert bucket_weekly_installs(9) == 5
    assert bucket_weekly_installs(10) == 15
    assert bucket_weekly_installs(100) == 30
    assert bucket_weekly_installs(1_000) == 50
    assert bucket_weekly_installs(10_000) == 70
    assert bucket_weekly_installs(50_000) == 90


def test_compute_impact_score_rewards_growth_and_penalizes_decline() -> None:
    assert compute_impact_score(current_weekly_installs=12_000, previous_weekly_installs=4_000) == 90
    assert compute_impact_score(current_weekly_installs=12_000, previous_weekly_installs=9_000) == 80
    assert compute_impact_score(current_weekly_installs=12_000, previous_weekly_installs=30_000) == 60


def test_impact_score_is_separate_from_risk_severity() -> None:
    medium = compute_priority_metrics(
        risk_score=65,
        severity="medium",
        confidence="likely",
        current_weekly_installs=1_200,
        previous_weekly_installs=900,
        peak_weekly_installs=1_200,
    )
    critical = compute_priority_metrics(
        risk_score=65,
        severity="critical",
        confidence="likely",
        current_weekly_installs=1_200,
        previous_weekly_installs=900,
        peak_weekly_installs=1_200,
    )

    assert isinstance(medium, ImpactMetrics)
    assert medium.impact_score == critical.impact_score
    assert critical.priority_score > medium.priority_score


def test_priority_increases_for_high_risk_high_install_skill() -> None:
    scores = compute_priority_metrics(
        risk_score=82,
        severity="high",
        confidence="likely",
        current_weekly_installs=12_000,
        previous_weekly_installs=4_000,
        peak_weekly_installs=12_000,
    )

    assert scores.install_delta == 8_000
    assert scores.peak_weekly_installs == 12_000
    assert scores.impact_score >= 80
    assert scores.priority_score > 82
