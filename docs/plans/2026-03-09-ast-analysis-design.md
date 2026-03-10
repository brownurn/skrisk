# Deep AST Analysis Design

Date: 2026-03-09

## Goal

Upgrade SK Risk from heuristic string scanning plus lightweight reconstruction into a deeper static analysis engine that can recover hidden URLs, domains, and exfiltration flows from Python, JavaScript, and shell skill content.

## Problem

The current analyzer already handles:

- printable Base64
- percent and unicode decoding
- bare domains
- simple JavaScript `String.fromCharCode(...)`
- simple Python string concatenation
- simple shell variable substitution

That catches straightforward hiding, but it still misses many real-world patterns:

- JavaScript string assembly via AST expressions, template literals, array joins, `atob`, and `decodeURIComponent`
- Python string assembly via `.join(...)`, `.format(...)`, f-strings, `%` formatting, and simple variable flow into request calls
- shell assignments and command arguments that need real parsing rather than regex splitting
- PowerShell `-enc` payloads
- hex-encoded strings and escaped blobs that turn into URLs or hostnames only after deeper reconstruction

## Design

### 1. Keep one analyzer pipeline

Do not add a second independent AST analyzer. Extend the existing variant-expansion layer so the main `SkillAnalyzer` still works like this:

1. decode and reconstruct more hidden payload variants
2. extract URLs and host indicators from those variants
3. score behavior and intel as one consistent report

That keeps the output model stable for persistence, UI, and risk scoring.

### 2. Add real parser-backed extraction

Use parser-backed extraction where it matters:

- Python: extend the current `ast` visitor into a small string/data-flow evaluator
- JavaScript: add a real JS AST parser so we can walk declarations, template literals, call expressions, member expressions, and simple decoders
- Shell: add a shell parser so variable assignments and command invocations are reconstructed structurally

The target is not full program execution. It is static recovery of high-signal string flows and network targets.

### 3. Expand decoder coverage

Add higher-signal decoders before URL/domain extraction:

- hex blob decoding
- PowerShell `-enc` UTF-16LE Base64 decoding
- nested decode chains where a decoded variant yields another structured variant

Each surfaced string should carry a variant kind so indicator provenance remains explainable.

### 4. Keep data flow bounded

This phase should handle common string-construction patterns, not arbitrary symbolic execution.

Boundaries:

- local assignments only
- simple function arguments only
- string-like literals, lists, tuples, and template pieces only
- no interprocedural whole-program solving

That is enough to materially improve exfiltration and downloader detection without turning the analyzer into a research project.

### 5. Reanalysis strategy

Once the AST-enabled analyzer lands, rerun the existing repo-first analysis over the mirrored corpus instead of building a new execution engine.

Operational shape:

- keep the existing producer at `24` workers on this `32` core host
- keep ingestion on Postgres
- use single-artifact or very small artifact claims for giant repos so large registries do not starve the tail

## Expected outcome

- more hidden URLs and domains extracted from current mirrored repos
- better detection of exfil and downloader behavior hidden behind simple encoding or string construction
- no change to the public risk-report schema
- immediate compatibility with the current Postgres/OpenSearch/Neo4j pipeline
