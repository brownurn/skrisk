import type { InstallHistoryEntry, SeverityLevel, SkillSummary } from '$lib/types';

export function severityTone(severity: string): 'critical' | 'high' | 'medium' {
	if (severity === 'critical') return 'critical';
	if (severity === 'high') return 'high';
	return 'medium';
}

export function severityRank(severity: SeverityLevel): number {
	switch (severity) {
		case 'critical':
			return 5;
		case 'high':
			return 4;
		case 'medium':
			return 3;
		case 'low':
			return 2;
		default:
			return 1;
	}
}

function formatCompactNumber(value: number): string {
	const absoluteValue = Math.abs(value);

	if (absoluteValue >= 1_000_000) {
		return `${(value / 1_000_000).toFixed(1)}m`;
	}

	if (absoluteValue >= 1_000) {
		return `${(value / 1_000).toFixed(1)}k`;
	}

	return String(value);
}

export function buildSkillHref(skill: Pick<SkillSummary, 'publisher' | 'repo' | 'skillSlug'>): string {
	return `/skills/${skill.publisher}/${skill.repo}/${skill.skillSlug}`;
}

export function buildIndicatorHref(indicatorType: string, indicatorValue: string): string {
	return `/indicators/${indicatorType}/${encodeURIComponent(indicatorValue)}`;
}

export function inferRegistrySource(url: string | null | undefined): string | null {
	if (!url) {
		return null;
	}

	const lowered = url.toLowerCase();
	if (lowered.includes('skills.sh')) {
		return 'skills.sh';
	}
	if (lowered.includes('skillsmp.com')) {
		return 'skillsmp';
	}
	return null;
}

export function registryLabels(skill: Pick<SkillSummary, 'sources' | 'installBreakdown' | 'registryUrl'>): string[] {
	if (skill.sources.length > 0) {
		return skill.sources;
	}

	const fromBreakdown = skill.installBreakdown
		.map((entry) => entry.sourceName)
		.filter((value, index, entries) => value.length > 0 && entries.indexOf(value) === index);
	if (fromBreakdown.length > 0) {
		return fromBreakdown;
	}

	const inferred = inferRegistrySource(skill.registryUrl);
	return inferred ? [inferred] : [];
}

export function firstDomain(domains: string[]): string {
	return domains[0] ?? 'No domain extracted';
}

export function formatOptional(value: string | null | undefined, fallback = 'Not available'): string {
	return value && value.trim().length > 0 ? value : fallback;
}

export function formatWeeklyInstalls(value: number | null | undefined, fallback = 'n/a'): string {
	if (value === null || value === undefined) {
		return fallback;
	}

	return formatCompactNumber(value);
}

export function formatInstallDelta(value: number | null | undefined, fallback = 'No baseline'): string {
	if (value === null || value === undefined) {
		return fallback;
	}

	if (value === 0) {
		return '0';
	}

	const prefix = value > 0 ? '+' : '-';
	return `${prefix}${formatCompactNumber(Math.abs(value))}`;
}

export function installTrendLabel(value: number | null | undefined): string {
	if (value === null || value === undefined) {
		return 'Awaiting second observation';
	}

	if (value > 0) {
		return `Up ${formatInstallDelta(value)}`;
	}

	if (value < 0) {
		return `Down ${formatInstallDelta(value)}`;
	}

	return 'Flat';
}

export function installTrendTone(value: number | null | undefined): 'success' | 'critical' | 'accent' {
	if (value === null || value === undefined || value === 0) {
		return 'accent';
	}

	return value > 0 ? 'success' : 'critical';
}

export function priorityTone(score: number | null | undefined): 'critical' | 'high' | 'medium' {
	if ((score ?? 0) >= 85) return 'critical';
	if ((score ?? 0) >= 60) return 'high';
	return 'medium';
}

export function priorityCardTone(score: number | null | undefined): 'critical' | 'accent' | 'success' {
	if ((score ?? 0) >= 85) return 'critical';
	if ((score ?? 0) >= 60) return 'accent';
	return 'success';
}

export function formatObservedAt(value: string | null | undefined, fallback = 'Not observed'): string {
	if (!value) {
		return fallback;
	}

	const parsed = new Date(value);
	if (Number.isNaN(parsed.getTime())) {
		return value;
	}

	const year = parsed.getUTCFullYear();
	const month = String(parsed.getUTCMonth() + 1).padStart(2, '0');
	const day = String(parsed.getUTCDate()).padStart(2, '0');
	const hours = String(parsed.getUTCHours()).padStart(2, '0');
	const minutes = String(parsed.getUTCMinutes()).padStart(2, '0');

	return `${year}-${month}-${day} ${hours}:${minutes} UTC`;
}

export function formatObservationKind(value: string | null | undefined): string {
	if (value === 'directory_fetch') {
		return 'Directory fetch';
	}

	if (value === 'scan_attribution') {
		return 'Scan attribution';
	}

	return formatOptional(value, 'Recorded telemetry');
}

export function formatInstallHistoryContext(entry: InstallHistoryEntry): string {
	const parts: string[] = [];

	if (entry.repoSnapshotId !== null) {
		parts.push(`snapshot #${entry.repoSnapshotId}`);
	}

	if (entry.registryRank !== null) {
		parts.push(`rank #${entry.registryRank}`);
	}

	const source = entry.rawPayload?.source;
	if (typeof source === 'string' && source.trim().length > 0) {
		parts.push(source);
	}

	return parts.join(' · ') || 'Recorded telemetry';
}
