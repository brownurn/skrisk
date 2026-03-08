import type {
	DashboardStats,
	FeedArtifact,
	FeedRunSummary,
	IndicatorDetail,
	IndicatorEnrichment,
	IndicatorMatch,
	IndicatorObservation,
	IndicatorSummary,
	InstallHistoryEntry,
	LinkedSkill,
	OverviewData,
	RiskFinding,
	RiskReport,
	SkillDetail,
	SkillPage,
	SkillIndicatorLink,
	SkillSnapshot,
	SkillSummary,
	VTQueueItem,
	VTQueueStatus
} from '$lib/types';

const API_BASE = (import.meta.env.PUBLIC_SKRISK_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '';

type Fetcher = typeof fetch;

async function requestJson<T>(fetcher: Fetcher, path: string): Promise<T> {
	const response = await fetcher(`${API_BASE}${path}`);
	if (!response.ok) {
		throw new Error(`API request failed for ${path}: ${response.status}`);
	}
	return (await response.json()) as T;
}

function emptySnapshot(): SkillSnapshot {
	return {
		id: 0,
		versionLabel: '',
		folderHash: '',
		referencedFiles: [],
		extractedDomains: [],
		riskReport: normalizeRiskReport(undefined),
		indicatorLinks: []
	};
}

function normalizeMaybeNumber(value: unknown): number | null {
	if (value === null || value === undefined || value === '') {
		return null;
	}

	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : null;
}

function normalizeStats(raw: Record<string, number>, pendingVtQueue: number): DashboardStats {
	return {
		trackedRepos: raw.tracked_repos ?? 0,
		trackedSkills: raw.tracked_skills ?? 0,
		criticalSkills: raw.critical_skills ?? 0,
		highRiskSkills: raw.high_risk_skills ?? 0,
		intelBackedFindings: raw.intel_backed_findings ?? 0,
		pendingVtQueue
	};
}

function normalizeRiskFinding(raw: Record<string, unknown>): RiskFinding {
	return {
		path: String(raw.path ?? ''),
		category: String(raw.category ?? ''),
		severity: String(raw.severity ?? ''),
		evidence: String(raw.evidence ?? '')
	};
}

function normalizeObservation(raw: Record<string, unknown>): IndicatorObservation {
	return {
		id: Number(raw.id ?? 0),
		sourceProvider: raw.source_provider ? String(raw.source_provider) : undefined,
		sourceFeed: raw.source_feed ? String(raw.source_feed) : undefined,
		classification: raw.classification ? String(raw.classification) : null,
		confidenceLabel: raw.confidence_label ? String(raw.confidence_label) : null,
		summary: raw.summary ? String(raw.summary) : null
	};
}

function normalizeIndicatorMatch(raw: Record<string, unknown>): IndicatorMatch {
	return {
		indicatorType: raw.indicator_type ? String(raw.indicator_type) : undefined,
		indicatorValue: raw.indicator_value ? String(raw.indicator_value) : undefined,
		observations: Array.isArray(raw.observations)
			? raw.observations.map((item) => normalizeObservation(item as Record<string, unknown>))
			: []
	};
}

function normalizeRiskReport(raw: Record<string, unknown> | undefined): RiskReport {
	return {
		severity: (raw?.severity as RiskReport['severity']) ?? 'none',
		score: Number(raw?.score ?? 0),
		behaviorScore: raw?.behavior_score ? Number(raw.behavior_score) : undefined,
		intelScore: raw?.intel_score ? Number(raw.intel_score) : undefined,
		changeScore: raw?.change_score ? Number(raw.change_score) : undefined,
		confidence: raw?.confidence ? String(raw.confidence) : undefined,
		categories: Array.isArray(raw?.categories) ? raw!.categories.map(String) : [],
		domains: Array.isArray(raw?.domains) ? raw!.domains.map(String) : [],
		findings: Array.isArray(raw?.findings)
			? raw!.findings.map((item) => normalizeRiskFinding(item as Record<string, unknown>))
			: [],
		indicatorMatches: Array.isArray(raw?.indicator_matches)
			? raw!.indicator_matches.map((item) => normalizeIndicatorMatch(item as Record<string, unknown>))
			: []
	};
}

function normalizeSkillIndicatorLink(raw: Record<string, unknown>): SkillIndicatorLink {
	return {
		indicatorId: raw.indicator_id ? Number(raw.indicator_id) : undefined,
		indicatorType: raw.indicator_type ? String(raw.indicator_type) : undefined,
		indicatorValue: raw.indicator_value ? String(raw.indicator_value) : undefined,
		sourcePath: raw.source_path ? String(raw.source_path) : null,
		extractionKind: raw.extraction_kind ? String(raw.extraction_kind) : null,
		rawValue: raw.raw_value ? String(raw.raw_value) : null,
		isNewInSnapshot: Boolean(raw.is_new_in_snapshot)
	};
}

function normalizeSnapshot(raw?: Record<string, unknown> | null): SkillSnapshot {
	if (!raw) {
		return emptySnapshot();
	}

	return {
		id: Number(raw.id ?? 0),
		versionLabel: String(raw.version_label ?? ''),
		folderHash: String(raw.folder_hash ?? ''),
		referencedFiles: Array.isArray(raw.referenced_files) ? raw.referenced_files.map(String) : [],
		extractedDomains: Array.isArray(raw.extracted_domains) ? raw.extracted_domains.map(String) : [],
		riskReport: normalizeRiskReport(raw.risk_report as Record<string, unknown> | undefined),
		indicatorLinks: Array.isArray(raw.indicator_links)
			? raw.indicator_links.map((item) => normalizeSkillIndicatorLink(item as Record<string, unknown>))
			: []
	};
}

function normalizeSkillSummary(raw: Record<string, unknown>): SkillSummary {
	return {
		publisher: String(raw.publisher ?? ''),
		repo: String(raw.repo ?? ''),
		skillSlug: String(raw.skill_slug ?? ''),
		title: String(raw.title ?? ''),
		currentWeeklyInstalls: normalizeMaybeNumber(raw.current_weekly_installs),
		currentWeeklyInstallsObservedAt: raw.current_weekly_installs_observed_at
			? String(raw.current_weekly_installs_observed_at)
			: null,
		peakWeeklyInstalls: normalizeMaybeNumber(raw.peak_weekly_installs),
		weeklyInstallsDelta: normalizeMaybeNumber(raw.weekly_installs_delta),
		impactScore: Number(raw.impact_score ?? 0),
		priorityScore: Number(raw.priority_score ?? 0),
		latestSnapshot: normalizeSnapshot(raw.latest_snapshot as Record<string, unknown>)
	};
}

function normalizeSkillPage(raw: Record<string, unknown>): SkillPage {
	const items = Array.isArray(raw.items)
		? raw.items.map((item) => normalizeSkillSummary(item as Record<string, unknown>))
		: [];

	return {
		items,
		total: Number(raw.total ?? items.length),
		page: Number(raw.page ?? 1),
		pageSize: Number(raw.page_size ?? items.length),
		hasNext: Boolean(raw.has_next),
		hasPrevious: Boolean(raw.has_previous)
	};
}

function normalizeInstallHistoryEntry(raw: Record<string, unknown>): InstallHistoryEntry {
	return {
		id: Number(raw.id ?? 0),
		skillId: Number(raw.skill_id ?? 0),
		registrySyncRunId: normalizeMaybeNumber(raw.registry_sync_run_id),
		repoSnapshotId: normalizeMaybeNumber(raw.repo_snapshot_id),
		observedAt: raw.observed_at ? String(raw.observed_at) : null,
		weeklyInstalls: normalizeMaybeNumber(raw.weekly_installs),
		registryRank: normalizeMaybeNumber(raw.registry_rank),
		observationKind: String(raw.observation_kind ?? ''),
		rawPayload:
			raw.raw_payload && typeof raw.raw_payload === 'object'
				? (raw.raw_payload as Record<string, unknown>)
				: null
	};
}

function normalizeExternalVerdict(raw: Record<string, unknown>) {
	return {
		partner: String(raw.partner ?? ''),
		verdict: String(raw.verdict ?? ''),
		summary: raw.summary ? String(raw.summary) : null,
		analyzedAt: raw.analyzed_at ? String(raw.analyzed_at) : null
	};
}

function normalizeFeedArtifact(raw: Record<string, unknown>): FeedArtifact {
	return {
		artifactType: String(raw.artifact_type ?? ''),
		relativePath: String(raw.relative_path ?? ''),
		contentType: raw.content_type ? String(raw.content_type) : null
	};
}

function normalizeFeedRun(raw: Record<string, unknown>): FeedRunSummary {
	return {
		id: Number(raw.id ?? 0),
		provider: String(raw.provider ?? ''),
		feedName: String(raw.feed_name ?? ''),
		sourceUrl: String(raw.source_url ?? ''),
		createdAt: raw.created_at ? String(raw.created_at) : null,
		artifacts: Array.isArray(raw.artifacts)
			? raw.artifacts.map((item) => normalizeFeedArtifact(item as Record<string, unknown>))
			: []
	};
}

function normalizeIndicatorSummary(raw: Record<string, unknown>): IndicatorSummary {
	return {
		id: Number(raw.id ?? 0),
		indicatorType: String(raw.indicator_type ?? ''),
		indicatorValue: String(raw.indicator_value ?? ''),
		normalizedValue: String(raw.normalized_value ?? '')
	};
}

function normalizeEnrichment(raw: Record<string, unknown>): IndicatorEnrichment {
	return {
		provider: String(raw.provider ?? ''),
		lookupKey: String(raw.lookup_key ?? ''),
		status: String(raw.status ?? ''),
		summary: raw.summary ? String(raw.summary) : null,
		archiveRelativePath: raw.archive_relative_path ? String(raw.archive_relative_path) : null
	};
}

function normalizeLinkedSkill(raw: Record<string, unknown>): LinkedSkill {
	return {
		publisher: String(raw.publisher ?? ''),
		repo: String(raw.repo ?? ''),
		skillSlug: String(raw.skill_slug ?? ''),
		snapshotId: Number(raw.snapshot_id ?? 0),
		versionLabel: String(raw.version_label ?? ''),
		sourcePath: raw.source_path ? String(raw.source_path) : null,
		extractionKind: raw.extraction_kind ? String(raw.extraction_kind) : null
	};
}

function normalizeQueueItem(raw: Record<string, unknown>): VTQueueItem {
	return {
		id: Number(raw.id ?? 0),
		indicatorId: Number(raw.indicator_id ?? 0),
		indicatorType: String(raw.indicator_type ?? ''),
		indicatorValue: String(raw.indicator_value ?? ''),
		priority: Number(raw.priority ?? 0),
		reason: String(raw.reason ?? ''),
		status: String(raw.status ?? ''),
		attemptCount: Number(raw.attempt_count ?? 0)
	};
}

export async function loadOverview(fetcher: Fetcher): Promise<OverviewData> {
	const [rawStats, rawCriticalSkills, rawFeedRuns, rawVtQueue] = await Promise.all([
		requestJson<Record<string, number>>(fetcher, '/api/stats'),
		requestJson<Record<string, unknown>[]>(fetcher, '/api/skills?severity=critical&limit=6'),
		requestJson<Record<string, unknown>[]>(fetcher, '/api/intel/feeds?limit=6'),
		requestJson<Record<string, unknown>>(fetcher, '/api/queue/vt')
	]);

	const criticalSkills = rawCriticalSkills.map((item) => normalizeSkillSummary(item));
	const vtQueue = normalizeQueueStatus(rawVtQueue);

	return {
		stats: normalizeStats(rawStats, vtQueue.queueItems.length),
		criticalSkills,
		feedRuns: rawFeedRuns.map((item) => normalizeFeedRun(item)),
		vtQueue
	};
}

export async function loadSkillsPage(
	fetcher: Fetcher,
	params: {
		page: number;
		pageSize: number;
		sort: 'priority' | 'installs' | 'risk' | 'growth';
		severity?: 'critical' | 'high' | 'medium' | 'low' | 'none';
		query?: string;
		minWeeklyInstalls?: number;
		maxWeeklyInstalls?: number;
	}
): Promise<SkillPage> {
	const searchParams = new URLSearchParams();
	searchParams.set('page', String(params.page));
	searchParams.set('page_size', String(params.pageSize));
	searchParams.set('sort', params.sort);
	if (params.severity) {
		searchParams.set('severity', params.severity);
	}
	if (params.query) {
		searchParams.set('q', params.query);
	}
	if (params.minWeeklyInstalls !== undefined) {
		searchParams.set('min_weekly_installs', String(params.minWeeklyInstalls));
	}
	if (params.maxWeeklyInstalls !== undefined) {
		searchParams.set('max_weekly_installs', String(params.maxWeeklyInstalls));
	}

	const rawPage = await requestJson<Record<string, unknown>>(
		fetcher,
		`/api/skills/page?${searchParams.toString()}`
	);
	return normalizeSkillPage(rawPage);
}

export async function loadSkillDetail(
	fetcher: Fetcher,
	publisher: string,
	repo: string,
	skillSlug: string
): Promise<SkillDetail> {
	const raw = await requestJson<Record<string, unknown>>(
		fetcher,
		`/api/skills/${publisher}/${repo}/${skillSlug}`
	);

	return {
		...normalizeSkillSummary(raw),
		relativePath: raw.relative_path ? String(raw.relative_path) : '',
		registryUrl: raw.registry_url ? String(raw.registry_url) : '',
		externalVerdicts: Array.isArray(raw.external_verdicts)
			? raw.external_verdicts.map((item) => normalizeExternalVerdict(item as Record<string, unknown>))
			: [],
		installHistory: Array.isArray(raw.install_history)
			? raw.install_history.map((item) => normalizeInstallHistoryEntry(item as Record<string, unknown>))
			: []
	};
}

export async function loadIndicators(fetcher: Fetcher): Promise<IndicatorSummary[]> {
	const rawIndicators = await requestJson<Record<string, unknown>[]>(fetcher, '/api/indicators?limit=100');
	return rawIndicators.map((item) => normalizeIndicatorSummary(item));
}

export async function loadIndicatorDetail(
	fetcher: Fetcher,
	indicatorType: string,
	indicatorValue: string
): Promise<IndicatorDetail> {
	const raw = await requestJson<Record<string, unknown>>(
		fetcher,
		`/api/indicators/${indicatorType}/${encodeURIComponent(indicatorValue)}`
	);

	return {
		indicator: normalizeIndicatorSummary(raw.indicator as Record<string, unknown>),
		observations: Array.isArray(raw.observations)
			? raw.observations.map((item) => normalizeObservation(item as Record<string, unknown>))
			: [],
		enrichments: Array.isArray(raw.enrichments)
			? raw.enrichments.map((item) => normalizeEnrichment(item as Record<string, unknown>))
			: [],
		linkedSkills: Array.isArray(raw.linked_skills)
			? raw.linked_skills.map((item) => normalizeLinkedSkill(item as Record<string, unknown>))
			: []
	};
}

export async function loadVTQueue(fetcher: Fetcher): Promise<VTQueueStatus> {
	const raw = await requestJson<Record<string, unknown>>(fetcher, '/api/queue/vt');
	return normalizeQueueStatus(raw);
}

function normalizeQueueStatus(raw: Record<string, unknown>): VTQueueStatus {
	return {
		dailyBudget: Number(raw.daily_budget ?? 0),
		dailyBudgetUsed: Number(raw.daily_budget_used ?? 0),
		dailyBudgetRemaining: Number(raw.daily_budget_remaining ?? 0),
		queueItems: Array.isArray(raw.queue_items)
			? raw.queue_items.map((item) => normalizeQueueItem(item as Record<string, unknown>))
			: []
	};
}
