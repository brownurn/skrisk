"""Policy helpers for country-risk classification."""

from __future__ import annotations

from typing import Final

_COUNTRY_BY_CODE: Final[dict[str, str]] = {
    "AF": "Afghanistan",
    "BY": "Belarus",
    "CN": "China",
    "CG": "Republic of the Congo",
    "CD": "Democratic Republic of the Congo",
    "CU": "Cuba",
    "DZ": "Algeria",
    "HT": "Haiti",
    "IR": "Iran",
    "KE": "Kenya",
    "LA": "Laos",
    "LB": "Lebanon",
    "MC": "Monaco",
    "MM": "Myanmar",
    "NA": "Namibia",
    "NG": "Nigeria",
    "KP": "North Korea",
    "RO": "Romania",
    "RU": "Russia",
    "SS": "South Sudan",
    "SY": "Syria",
    "TZ": "Tanzania",
    "UA": "Ukraine",
    "VE": "Venezuela",
    "VN": "Vietnam",
    "YE": "Yemen",
    "US": "United States",
}

_ALIASES: Final[dict[str, tuple[str, str]]] = {
    "afghanistan": ("AF", "Afghanistan"),
    "belarus": ("BY", "Belarus"),
    "china": ("CN", "China"),
    "congo": ("CG", "Republic of the Congo"),
    "republic of the congo": ("CG", "Republic of the Congo"),
    "democratic republic of the congo": ("CD", "Democratic Republic of the Congo"),
    "dr congo": ("CD", "Democratic Republic of the Congo"),
    "drc": ("CD", "Democratic Republic of the Congo"),
    "cuba": ("CU", "Cuba"),
    "algeria": ("DZ", "Algeria"),
    "haiti": ("HT", "Haiti"),
    "iran": ("IR", "Iran"),
    "kenya": ("KE", "Kenya"),
    "laos": ("LA", "Laos"),
    "lebanon": ("LB", "Lebanon"),
    "monaco": ("MC", "Monaco"),
    "myanmar": ("MM", "Myanmar"),
    "burma": ("MM", "Myanmar"),
    "namibia": ("NA", "Namibia"),
    "nigeria": ("NG", "Nigeria"),
    "north korea": ("KP", "North Korea"),
    "romania": ("RO", "Romania"),
    "russia": ("RU", "Russia"),
    "south sudan": ("SS", "South Sudan"),
    "syria": ("SY", "Syria"),
    "tanzania": ("TZ", "Tanzania"),
    "tanazania": ("TZ", "Tanzania"),
    "ukraine": ("UA", "Ukraine"),
    "venezuela": ("VE", "Venezuela"),
    "vietnam": ("VN", "Vietnam"),
    "yemen": ("YE", "Yemen"),
    "united states": ("US", "United States"),
}

_PRIMARY_CYBER_CONCERN_CODES: Final[set[str]] = {
    "AF",
    "BY",
    "CN",
    "CG",
    "CD",
    "CU",
    "DZ",
    "HT",
    "IR",
    "KE",
    "LA",
    "LB",
    "MC",
    "MM",
    "NA",
    "NG",
    "KP",
    "RO",
    "RU",
    "SS",
    "SY",
    "TZ",
    "UA",
    "VE",
    "VN",
    "YE",
}


def evaluate_country_risk(
    *,
    country_code: str | None = None,
    country_name: str | None = None,
) -> dict[str, str | bool | None]:
    normalized_code = (country_code or "").strip().upper() or None
    normalized_name = (country_name or "").strip() or None

    alias_key = normalized_name.lower() if normalized_name else None
    if alias_key and alias_key in _ALIASES:
        normalized_code, normalized_name = _ALIASES[alias_key]
    elif normalized_code and normalized_code in _COUNTRY_BY_CODE:
        normalized_name = _COUNTRY_BY_CODE[normalized_code]

    return {
        "country_code": normalized_code,
        "country_name": normalized_name,
        "is_primary_cyber_concern": bool(
            normalized_code and normalized_code in _PRIMARY_CYBER_CONCERN_CODES
        ),
    }
