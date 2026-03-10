import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import OverviewPage from './+page.svelte';

test('renders intel-backed dashboard metrics', () => {
	render(OverviewPage, {
		data: {
			stats: {
				trackedRepos: 10,
				trackedSkills: 120,
				criticalSkills: 4,
				highRiskSkills: 11,
				intelBackedFindings: 8,
				pendingVtQueue: 3
			},
			criticalSkills: [
				{
					publisher: 'tul-sh',
					repo: 'skills',
					skillSlug: 'agent-tools',
					title: 'Agent Tools',
					currentWeeklyInstalls: 12_500,
					currentWeeklyInstallsObservedAt: '2026-03-07T08:00:00+00:00',
					currentTotalInstalls: 12_500,
					currentTotalInstallsObservedAt: '2026-03-07T08:00:00+00:00',
					peakWeeklyInstalls: 18_000,
					weeklyInstallsDelta: 3_000,
					impactScore: 90,
					priorityScore: 94,
					sourceCount: 2,
					sources: ['skills.sh', 'skillsmp'],
					installBreakdown: [
						{
							sourceName: 'skills.sh',
							weeklyInstalls: 12_500,
							sourceUrl: 'https://skills.sh/tul-sh/skills/agent-tools',
							registryRank: 1
						},
						{
							sourceName: 'skillsmp',
							weeklyInstalls: 0,
							sourceUrl: 'https://skillsmp.com/skills/example-agent-tools',
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
							severity: 'critical',
							score: 88,
							behaviorScore: 55,
							intelScore: 22,
							changeScore: 11,
							confidence: 'likely',
							categories: ['exfiltration'],
							domains: ['drop.example'],
							findings: [],
							indicatorMatches: []
						}
					}
				}
			],
			flaggedRepos: [
				{
					publisher: 'tul-sh',
					repo: 'skills',
					flaggedSkillCount: 2,
					criticalSkillCount: 1,
					topSeverity: 'critical',
					topRiskScore: 88,
					totalInstalls: 12_500
				}
			],
			feedRuns: [],
			vtQueue: {
				dailyBudget: 490,
				dailyBudgetUsed: 20,
				dailyBudgetRemaining: 470,
				queueItems: []
			}
		}
	});

	expect(screen.getByText('Intel-Backed Findings')).toBeInTheDocument();
	expect(screen.getByText('Pending VT Queue')).toBeInTheDocument();
	expect(screen.getAllByRole('columnheader', { name: /installs/i }).length).toBeGreaterThan(0);
	expect(screen.getByRole('columnheader', { name: /registries/i })).toBeInTheDocument();
	expect(screen.getByRole('heading', { name: /flagged repos/i })).toBeInTheDocument();
	expect(screen.getByText('2 flagged skills')).toBeInTheDocument();
	expect(screen.getAllByText('12.5k').length).toBeGreaterThan(0);
	expect(screen.getByText('skills.sh')).toBeInTheDocument();
	expect(screen.getByText('skillsmp')).toBeInTheDocument();
	expect(screen.getAllByText('8').length).toBeGreaterThan(0);
});
