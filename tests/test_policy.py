from __future__ import annotations

from skrisk.policy import evaluate_country_risk


def test_evaluate_country_risk_marks_primary_cyber_concern_countries() -> None:
    result = evaluate_country_risk(country_code="CN", country_name="China")

    assert result["country_code"] == "CN"
    assert result["country_name"] == "China"
    assert result["is_primary_cyber_concern"] is True


def test_evaluate_country_risk_normalizes_user_tanzania_alias() -> None:
    result = evaluate_country_risk(country_name="Tanazania")

    assert result["country_name"] == "Tanzania"
    assert result["country_code"] == "TZ"
    assert result["is_primary_cyber_concern"] is True


def test_evaluate_country_risk_treats_both_congo_variants_as_primary_concern() -> None:
    republic = evaluate_country_risk(country_name="Republic of the Congo")
    democratic = evaluate_country_risk(country_code="CD", country_name="Democratic Republic of the Congo")

    assert republic["is_primary_cyber_concern"] is True
    assert democratic["is_primary_cyber_concern"] is True


def test_evaluate_country_risk_keeps_unlisted_country_outside_primary_concern() -> None:
    result = evaluate_country_risk(country_code="US", country_name="United States")

    assert result["country_code"] == "US"
    assert result["country_name"] == "United States"
    assert result["is_primary_cyber_concern"] is False

