import type { PageLoad } from './$types';
import { loadSkillsPage } from '$lib/api';
import type { SeverityLevel, SkillsPageFilters } from '$lib/types';

type InstallBucket = SkillsPageFilters['installBucket'];
type SortMode = SkillsPageFilters['sort'];

const DEFAULT_PAGE_SIZE = 100;
const VALID_INSTALL_BUCKETS: InstallBucket[] = ['all', '0-9', '10-99', '100-999', '1k-9.9k', '10k+'];
const VALID_SORT_MODES: SortMode[] = ['priority', 'installs', 'risk', 'growth'];
const VALID_SEVERITIES: Array<SeverityLevel | 'all'> = ['all', 'critical', 'high', 'medium', 'low', 'none'];

function normalizePage(value: string | null): number {
	const parsed = Number(value ?? 1);
	if (!Number.isFinite(parsed) || parsed < 1) {
		return 1;
	}
	return Math.floor(parsed);
}

function normalizeInstallBucket(value: string | null): InstallBucket {
	return VALID_INSTALL_BUCKETS.includes(value as InstallBucket) ? (value as InstallBucket) : 'all';
}

function normalizeSort(value: string | null): SortMode {
	return VALID_SORT_MODES.includes(value as SortMode) ? (value as SortMode) : 'priority';
}

function normalizeSeverity(value: string | null): SeverityLevel | 'all' {
	return VALID_SEVERITIES.includes(value as SeverityLevel | 'all')
		? (value as SeverityLevel | 'all')
		: 'all';
}

function installBounds(bucket: InstallBucket): { min?: number; max?: number } {
	switch (bucket) {
		case '0-9':
			return { min: 0, max: 9 };
		case '10-99':
			return { min: 10, max: 99 };
		case '100-999':
			return { min: 100, max: 999 };
		case '1k-9.9k':
			return { min: 1_000, max: 9_999 };
		case '10k+':
			return { min: 10_000 };
		default:
			return {};
	}
}

export const load: PageLoad = async ({ fetch, url }) => {
	const page = normalizePage(url.searchParams.get('page'));
	const query = (url.searchParams.get('q') ?? '').trim();
	const severity = normalizeSeverity(url.searchParams.get('severity'));
	const installBucket = normalizeInstallBucket(url.searchParams.get('installs'));
	const sort = normalizeSort(url.searchParams.get('sort'));
	const bounds = installBounds(installBucket);

	return {
		page: await loadSkillsPage(fetch, {
			page,
			pageSize: DEFAULT_PAGE_SIZE,
			sort,
			severity: severity === 'all' ? undefined : severity,
			query: query || undefined,
			minWeeklyInstalls: bounds.min,
			maxWeeklyInstalls: bounds.max
		}),
		filters: {
			query,
			severity,
			installBucket,
			sort
		} satisfies SkillsPageFilters
	};
};
