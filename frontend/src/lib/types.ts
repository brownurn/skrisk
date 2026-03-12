export type SeverityLevel = 'none' | 'low' | 'medium' | 'high' | 'critical';

export interface DashboardStats {
	trackedRepos: number;
	trackedSkills: number;
	criticalSkills: number;
	highRiskSkills: number;
	intelBackedFindings: number;
	pendingVtQueue: number;
}

export interface RiskFinding {
	path: string;
	category: string;
	severity: string;
	evidence: string;
	context?: string;
	details?: Record<string, unknown> | null;
}

export interface IndicatorObservation {
	id?: number;
	sourceProvider?: string;
	sourceFeed?: string;
	classification?: string | null;
	confidenceLabel?: string | null;
	summary?: string | null;
}

export interface IndicatorMatch {
	indicatorType?: string;
	indicatorValue?: string;
	observations: IndicatorObservation[];
}

export interface RiskReport {
	severity: SeverityLevel;
	score: number;
	behaviorScore?: number;
	intelScore?: number;
	changeScore?: number;
	confidence?: string;
	categories: string[];
	domains: string[];
	findings: RiskFinding[];
	indicatorMatches: IndicatorMatch[];
}

export interface SkillIndicatorLink {
	indicatorId?: number;
	indicatorType?: string;
	indicatorValue?: string;
	sourcePath?: string | null;
	extractionKind?: string | null;
	rawValue?: string | null;
	isNewInSnapshot?: boolean;
	enrichments?: IndicatorEnrichment[];
}

export interface SkillSnapshot {
	id: number;
	versionLabel: string;
	folderHash: string;
	referencedFiles: string[];
	extractedDomains: string[];
	riskReport: RiskReport;
	indicatorLinks?: SkillIndicatorLink[];
}

export interface InstallHistoryEntry {
	id: number;
	skillId: number;
	registrySyncRunId: number | null;
	repoSnapshotId: number | null;
	observedAt: string | null;
	weeklyInstalls: number | null;
	registryRank: number | null;
	observationKind: string;
	rawPayload: Record<string, unknown> | null;
}

export interface SourceInstallBreakdown {
	sourceName: string;
	weeklyInstalls: number | null;
	sourceUrl: string;
	registryRank: number | null;
}

export interface SkillSourceEntry extends SourceInstallBreakdown {
	id: number;
	registrySourceId: number;
	sourceBaseUrl: string;
	sourceNativeId: string | null;
	currentRegistrySyncRunId: number | null;
	currentRegistrySyncObservedAt: string | null;
	view: string;
	firstSeenAt: string | null;
	lastSeenAt: string | null;
	rawPayload: Record<string, unknown> | null;
}

export interface SkillSummary {
	publisher: string;
	repo: string;
	skillSlug: string;
	title: string;
	registryUrl?: string | null;
	currentWeeklyInstalls: number | null;
	currentWeeklyInstallsObservedAt: string | null;
	currentTotalInstalls: number | null;
	currentTotalInstallsObservedAt: string | null;
	peakWeeklyInstalls: number | null;
	weeklyInstallsDelta: number | null;
	impactScore: number;
	priorityScore: number;
	sourceCount: number;
	sources: string[];
	installBreakdown: SourceInstallBreakdown[];
	latestSnapshot: SkillSnapshot;
}

export interface SkillPage {
	items: SkillSummary[];
	total: number;
	page: number;
	pageSize: number;
	hasNext: boolean;
	hasPrevious: boolean;
}

export interface SkillsPageFilters {
	query: string;
	severity: SeverityLevel | 'all';
	installBucket: 'all' | '0-9' | '10-99' | '100-999' | '1k-9.9k' | '10k+';
	sort: 'priority' | 'installs' | 'risk' | 'growth';
}

export interface ExternalVerdict {
	partner: string;
	verdict: string;
	summary?: string | null;
	analyzedAt?: string | null;
}

export interface SkillDetail extends SkillSummary {
	relativePath?: string;
	registryUrl?: string;
	externalVerdicts: ExternalVerdict[];
	installHistory: InstallHistoryEntry[];
	sourceEntries: SkillSourceEntry[];
	outboundEvidence: OutboundEvidence[];
}

export interface OutboundDestination {
	ip: string;
	countryCode?: string | null;
	countryName?: string | null;
	asnName?: string | null;
	isPrimaryCyberConcern: boolean;
}

export interface OutboundEvidence {
	path: string;
	category: string;
	severity: string;
	context?: string | null;
	evidence: string;
	sourceKind?: string | null;
	sourceValues: string[];
	sinkKind?: string | null;
	sinkUrl?: string | null;
	sinkHost?: string | null;
	transportDetail?: string | null;
	destinations: OutboundDestination[];
	hasPrimaryCyberConcernDestination: boolean;
}

export interface FeedArtifact {
	artifactType: string;
	relativePath: string;
	contentType?: string | null;
}

export interface FeedRunSummary {
	id: number;
	provider: string;
	feedName: string;
	sourceUrl: string;
	createdAt?: string | null;
	artifacts?: FeedArtifact[];
}

export interface IndicatorSummary {
	id: number;
	indicatorType: string;
	indicatorValue: string;
	normalizedValue: string;
}

export interface IndicatorEnrichment {
	provider: string;
	lookupKey: string;
	status: string;
	summary?: string | null;
	archiveRelativePath?: string | null;
}

export interface LinkedSkill {
	publisher: string;
	repo: string;
	skillSlug: string;
	snapshotId: number;
	versionLabel: string;
	sourcePath?: string | null;
	extractionKind?: string | null;
}

export interface IndicatorDetail {
	indicator: IndicatorSummary;
	observations: IndicatorObservation[];
	enrichments: IndicatorEnrichment[];
	linkedSkills: LinkedSkill[];
}

export interface VTQueueItem {
	id: number;
	indicatorId: number;
	indicatorType: string;
	indicatorValue: string;
	priority: number;
	reason: string;
	status: string;
	attemptCount: number;
}

export interface VTQueueStatus {
	dailyBudget: number;
	dailyBudgetUsed: number;
	dailyBudgetRemaining: number;
	queueItemCount?: number;
	queueItems: VTQueueItem[];
}

export interface FlaggedRepoSummary {
	publisher: string;
	repo: string;
	flaggedSkillCount: number;
	criticalSkillCount: number;
	topSeverity: SeverityLevel;
	topRiskScore: number;
	totalInstalls: number;
}

export interface RepoDetail extends FlaggedRepoSummary {
	sourceUrl: string | null;
	skills: SkillSummary[];
}

export interface OverviewData {
	stats: DashboardStats;
	criticalSkills: SkillSummary[];
	flaggedRepos: FlaggedRepoSummary[];
	feedRuns: FeedRunSummary[];
	vtQueue: VTQueueStatus;
}
