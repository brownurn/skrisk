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

export interface SkillSummary {
	publisher: string;
	repo: string;
	skillSlug: string;
	title: string;
	latestSnapshot: SkillSnapshot;
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
	queueItems: VTQueueItem[];
}

export interface OverviewData {
	stats: DashboardStats;
	criticalSkills: SkillSummary[];
	feedRuns: FeedRunSummary[];
	vtQueue: VTQueueStatus;
}
