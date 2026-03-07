import type { SeverityLevel, SkillSummary } from '$lib/types';

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

export function buildSkillHref(skill: Pick<SkillSummary, 'publisher' | 'repo' | 'skillSlug'>): string {
	return `/skills/${skill.publisher}/${skill.repo}/${skill.skillSlug}`;
}

export function buildIndicatorHref(indicatorType: string, indicatorValue: string): string {
	return `/indicators/${indicatorType}/${encodeURIComponent(indicatorValue)}`;
}

export function firstDomain(domains: string[]): string {
	return domains[0] ?? 'No domain extracted';
}

export function formatOptional(value: string | null | undefined, fallback = 'Not available'): string {
	return value && value.trim().length > 0 ? value : fallback;
}
