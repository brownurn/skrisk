# Exfiltration Evidence And Country Risk Design

## Goal

Make SK Risk explain outbound risk with specific evidence instead of generic exfiltration strings, and classify destination countries against an explicit Melurna-maintained `primary cyber concern` policy set.

## Approved Direction

- Treat the user-provided country list as SK Risk policy input.
- Normalize obvious aliases and user typos:
  - `Tanazania` -> `Tanzania`
  - `Congo` -> both `Republic of the Congo` and `Democratic Republic of the Congo`
- Do not claim `data_exfiltration` unless SK Risk can identify:
  - a concrete sensitive source
  - a concrete remote sink
  - a direct operational execution context
- Distinguish ordinary credentialed API usage from true secret/file exfiltration.
- Surface destination IP/country/high-risk-country status on the skill detail page.

## Policy Model

Introduce a policy helper that accepts either country code or country name and returns:

- `country_code`
- `country_name`
- `normalized_country_name`
- `is_primary_cyber_concern`

Primary-cyber-concern set for this phase:

- Afghanistan
- Belarus
- China
- Congo
- Cuba
- Algeria
- Haiti
- Iran
- Kenya
- Laos
- Lebanon
- Monaco
- Myanmar
- Namibia
- Nigeria
- North Korea
- Romania
- Russia
- South Sudan
- Syria
- Tanzania
- Ukraine
- Venezuela
- Vietnam
- Yemen

## Evidence Model

Current `Finding.evidence` is just a string. That is too vague for outbound-risk review. Add optional structured details for outbound findings:

- `kind`
  - `secret_exfiltration`
  - `credential_transmission`
- `source_kind`
  - `env_var`
  - `secret_path`
  - `cookie`
  - `authorization_header`
  - `local_file`
- `source_values`
  - exact tokens or paths observed, such as `AWS_SECRET_ACCESS_KEY`, `BOCHA_API_KEY`, `~/.ssh/id_rsa`
- `sink_kind`
  - `curl`
  - `fetch`
  - `requests.post`
  - `httpx.post`
  - `axios.post`
- `sink_url`
- `sink_host`
- `transport_detail`
  - short explanation such as `Authorization header`, `multipart form upload`, `JSON body`

Scoring intent:

- `secret_exfiltration` remains high-risk behavior.
- `credential_transmission` is recorded and explained, but does not automatically imply malware or theft.
- Reference/example docs remain downgraded.

## UI/Analyst Experience

Add a new evidence rendering path on the skill detail page:

- `Hard evidence`
  - continue listing confirmed high-severity findings
- `Outbound evidence`
  - show each structured outbound finding with:
    - what was sent
    - how it was sent
    - where it was sent
    - resolved IPs
    - resolved countries
    - primary-cyber-concern badge when applicable

If a skill only has documentation examples, the page should clearly say that no operational outbound evidence was confirmed.

## Example Template

`clean-ddd-hexagonal` is the false-positive example: no real exfiltration, only reference material.

Use a different skill as the positive template. The first candidate to model is `176336109/.openclaw/bocha-web-search`, because it contains a direct outbound POST to `api.bocha.cn` with an authorization token. It is useful as a geography and credential-transmission example even if it is not a confirmed secret-theft example.

## Implementation Scope

Phase 1 in this change:

- Add policy helper.
- Add structured outbound evidence details to analyzer findings.
- Add skill-detail API shaping for country/IP evidence.
- Update the Svelte skill detail page.
- Rescore focused example skills after implementation.

Phase 2 after this lands:

- Recompute country-aware severity across the corpus after infra enrichment is present for more skills.
- Add outbound-country rollups to overview/repo pages.
