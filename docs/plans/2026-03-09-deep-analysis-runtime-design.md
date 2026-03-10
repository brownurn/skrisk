# Deep Analysis Runtime Design

Date: March 9, 2026

## Goal

Add a deeper static-analysis engine to SK Risk that can uncover hidden domains, URLs, and suspicious execution paths from mirrored repositories, then run that analysis continuously across the existing corpus with CPU-bound parallelism while preserving explainable evidence.

## Current State

- SK Risk already mirrors GitHub repositories under `data/mirrors/`.
- The current analyzer is heuristic and URL-centric. It expands printable Base64, detects a few high-signal execution and exfiltration patterns, and extracts literal URLs plus hostnames.
- The main registry scan path mirrors one repo and analyzes the registry-listed skill entries, but it does not yet promote repo-first analysis of every discovered skill in that checkout.
- Infrastructure enrichment exists for `local_dns`, `mewhois`, and `meip`.
- Abuse.ch observations are present, but VT processing has not been consumed yet.

## Requirements

- Analyze mirrored repos, not only registry-listed skills.
- Discover and analyze every skill directory in a mirrored repo checkout.
- Add a deeper static-analysis layer that can surface hidden network indicators and suspicious execution primitives.
- Run analysis with CPU-bound parallelism using about `80%` of host CPU cores.
- Preserve explainable evidence and extraction provenance.
- Feed the existing indicator, enrichment, search, and graph layers with richer results.

## Approach Options

### 1. Extend The Current Heuristic Analyzer

Keep regex-driven analysis and add more decoders plus some string reconstruction.

Pros:
- Fastest implementation
- Minimal architectural change

Cons:
- Hard to reason about language-specific constructs
- Limited ability to understand shell, JS, and Python code paths

### 2. Add A Lightweight AST/Data-Flow Layer On Top Of Existing Heuristics

Add language-aware passes for shell, JavaScript/TypeScript, and Python while keeping the current heuristic layer for broad file coverage.

Pros:
- Better hidden-domain discovery
- Better command reconstruction
- Keeps the current evidence model and storage layout

Cons:
- More implementation effort
- Some constructs still require best-effort approximations

### 3. Full Sandboxed Execution / Emulation

Run skills in controlled environments and observe live behavior.

Pros:
- Strongest visibility for runtime behavior

Cons:
- Unsafe and operationally expensive for this phase
- Not needed before improving static coverage

## Recommendation

Use option `2`.

Build a layered analysis pipeline:

- text/encoding expansion
- language-specific AST or structural passes
- suspicious capability detection
- indicator extraction with provenance
- repo-first persistence into the existing SK Risk model

This gets materially better hidden-domain and malware detection without waiting for a later detonation environment.

## Architecture

### 1. Layered Analyzer

Add a new analyzer stack:

- `expansion` layer
  - Base64
  - hex blobs
  - percent decoding
  - unicode escape decoding
  - shell-safe quoted string normalization
  - common charcode reconstruction
- `language` layer
  - shell command parsing and string joining
  - Python string literal / callsite extraction
  - JavaScript/TypeScript string literal / concatenation / `String.fromCharCode` extraction
- `indicator` layer
  - literal URLs
  - bare domains and hostnames
  - derived domains from reconstructed strings
  - IP addresses
- `behavior` layer
  - downloader chains
  - shell execution
  - encoded execution
  - exfiltration primitives
  - persistence and covert helper behavior

The final risk report remains evidence-first and explainable.

### 2. Repo-First Analysis

Promote repo snapshots to the primary scan unit:

- mirror the repo once
- discover every skill directory in that checkout
- analyze every discovered skill
- record repo-level evidence for shared helper files outside individual skill folders later as a second pass

Registry entries remain provenance and install telemetry, not the sole list of skills to analyze.

### 3. Continuous CPU-Bound Runtime

Add a dedicated analysis runner that:

- walks mirrored repos already on disk
- schedules repo-level analysis work
- uses a `ProcessPoolExecutor` sized to about `floor(cpu_count * 0.8)`
- writes results back through the existing repository/service layer
- can run continuously until the mirrored corpus is drained

Use process-based parallelism, not threads, because decoding, parsing, and string reconstruction are CPU-bound.

### 4. Relational Output

Richer analysis should directly improve:

- `skill_indicator_links`
- infrastructure enrichment candidates
- OpenSearch documents
- Neo4j graph projection

This phase should not redesign the DB. It should enrich the existing risk graph with better indicator extraction and repo-first coverage.

## Data Model Changes

The current schema is mostly sufficient. The main additions should be:

- richer `extraction_kind` values
- optional language or analysis metadata in serialized risk reports
- new repo-discovered discovery status for skills not listed in registries

No large schema rewrite is required for the first deep-analysis phase.

## Classification Changes

Add explicit discovery and impact status:

- `discovery_status`
  - `listed`
  - `multi_listed`
  - `unlisted`
- `impact_status`
  - `known`
  - `unknown`

Unlisted skills must still be fully risk-scored, but they should not receive fabricated install counts.

## Runtime And Operations

- Target CPU usage: about `80%` of host logical cores
- Backpressure should be repo-based, not skill-based
- The runtime should write progress logs and support resumable operation
- The initial pass should run against the current mirrored corpus before waiting for additional registry growth

## Testing Strategy

- unit tests for each decoder and AST extractor
- integration tests proving repo-first analysis persists snapshots for discovered-but-unlisted skills
- CLI tests for the new analysis runner
- regression tests that hidden domains encoded in strings are extracted
- enrichment tests confirming deeper indicators flow into `mewhois` / `meip` candidate selection

## Rollout Order

1. Deep decoding and extraction primitives
2. Shell/Python/JS structural analyzers
3. Repo-first scan service and CLI
4. Continuous process-pool runtime
5. Infra enrichment rerun
6. Search and graph refresh
