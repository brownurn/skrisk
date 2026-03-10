import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { within } from '@testing-library/dom';
import { expect, test } from 'vitest';
import type { SkillSummary } from '$lib/types';
import SkillsPage from './+page.svelte';

function buildSkill(
	skillSlug: string,
	priorityScore: number,
	installs: number,
	overrides: Partial<SkillSummary> = {}
): SkillSummary {
	return {
		publisher: 'tul-sh',
		repo: 'skills',
		skillSlug,
		title: skillSlug,
		registryUrl: `https://skills.sh/tul-sh/skills/${skillSlug}`,
		currentWeeklyInstalls: installs,
		currentWeeklyInstallsObservedAt: '2026-03-07T08:00:00+00:00',
		currentTotalInstalls: installs,
		currentTotalInstallsObservedAt: '2026-03-07T08:00:00+00:00',
		peakWeeklyInstalls: installs,
		weeklyInstallsDelta: 300,
		impactScore: 90,
		priorityScore,
		sourceCount: 2,
		sources: ['skills.sh', 'skillsmp'],
		installBreakdown: [
			{
				sourceName: 'skills.sh',
				weeklyInstalls: installs,
				sourceUrl: `https://skills.sh/tul-sh/skills/${skillSlug}`,
				registryRank: 1
			},
			{
				sourceName: 'skillsmp',
				weeklyInstalls: 0,
				sourceUrl: `https://skillsmp.com/skills/${skillSlug}`,
				registryRank: null
			}
		],
		latestSnapshot: {
			id: 14,
			versionLabel: 'v1.3.0',
			folderHash: 'abc123',
			referencedFiles: ['SKILL.md'],
			extractedDomains: ['drop.example'],
			riskReport: {
				severity: 'medium',
				score: 60,
				behaviorScore: 55,
				intelScore: 22,
				changeScore: 11,
				confidence: 'likely',
				categories: ['exfiltration'],
				domains: ['drop.example'],
				findings: [],
				indicatorMatches: [{ indicatorType: 'domain', indicatorValue: 'drop.example', observations: [] }]
			}
		},
		...overrides
	};
}

test('renders the server-provided page of skills with weekly installs', () => {
	const { container } = render(SkillsPage, {
		data: {
			page: {
				items: [buildSkill('agent-tools', 94, 12_000), buildSkill('network-probe', 32, 999)],
				total: 241,
				page: 2,
				pageSize: 50,
				hasNext: true,
				hasPrevious: true
			},
			filters: {
				query: 'agent',
				severity: 'high',
				installBucket: '10k+',
				sort: 'priority'
			}
		}
	});

	expect(screen.getByRole('heading', { name: 'Skills registry' })).toBeInTheDocument();
	expect(screen.getByText('Matching skills')).toBeInTheDocument();
	expect(screen.getByText('241')).toBeInTheDocument();
	expect(screen.getByRole('columnheader', { name: /installs/i })).toBeInTheDocument();
	expect(screen.getByRole('columnheader', { name: /registries/i })).toBeInTheDocument();
	expect(screen.getByRole('columnheader', { name: /flagged/i })).toBeInTheDocument();
	expect(screen.getByRole('columnheader', { name: /priority/i })).toBeInTheDocument();
	expect(screen.getByText('12.0k')).toBeInTheDocument();
	expect(screen.getByText('94')).toBeInTheDocument();
	expect(screen.getByText('Flagged')).toBeInTheDocument();
	expect(screen.getAllByText('skills.sh').length).toBeGreaterThan(0);
	expect(screen.getAllByText('skillsmp').length).toBeGreaterThan(0);
	expect(screen.getByDisplayValue('agent')).toBeInTheDocument();

	const rows = within(container).getAllByRole('row');
	expect(within(rows[1]).getByRole('link', { name: 'tul-sh/skills/agent-tools' })).toBeInTheDocument();
});

test('explains analyst columns and falls back to inferred registries when explicit sources are missing', () => {
	render(SkillsPage, {
		data: {
			page: {
				items: [
					buildSkill('seed-only', 0, 42, {
						sourceCount: 0,
						sources: [],
						installBreakdown: [],
						registryUrl: 'https://skills.sh/melurna/skill-pack/seed-only'
					})
				],
				total: 1,
				page: 1,
				pageSize: 100,
				hasNext: false,
				hasPrevious: false
			},
			filters: {
				query: '',
				severity: 'all',
				installBucket: 'all',
				sort: 'priority'
			}
		}
	});

	expect(screen.getAllByTitle(/B = behavior score/i).length).toBeGreaterThan(0);
	expect(screen.getAllByTitle(/Priority combines the latest risk score/i).length).toBeGreaterThan(0);
	expect(screen.getAllByTitle(/Top domain shows the first extracted domain/i).length).toBeGreaterThan(0);
	expect(screen.getAllByText('skills.sh').length).toBeGreaterThan(0);
});

test('renders pagination links that preserve filter state', () => {
	const { container } = render(SkillsPage, {
		data: {
			page: {
				items: [buildSkill('triage-first', 95, 120), buildSkill('reach-first', 60, 24_000)],
				total: 241,
				page: 2,
				pageSize: 50,
				hasNext: true,
				hasPrevious: true
			},
			filters: {
				query: 'reach',
				severity: 'critical',
				installBucket: '100-999',
				sort: 'installs'
			}
		}
	});

	const nextLink = within(container).getByRole('link', { name: /next page/i });
	expect(nextLink).toHaveAttribute(
		'href',
		'/skills?page=3&q=reach&severity=critical&installs=100-999&sort=installs'
	);
	expect(within(container).getByRole('link', { name: /previous page/i })).toHaveAttribute(
		'href',
		'/skills?page=1&q=reach&severity=critical&installs=100-999&sort=installs'
	);
});
