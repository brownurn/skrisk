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
					currentWeeklyInstalls: 12_000,
					currentWeeklyInstallsObservedAt: '2026-03-07T08:00:00+00:00',
					peakWeeklyInstalls: 18_000,
					weeklyInstallsDelta: 3_000,
					impactScore: 90,
					priorityScore: 94,
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
	expect(screen.getByRole('columnheader', { name: /weekly installs/i })).toBeInTheDocument();
	expect(screen.getByText('12.0k')).toBeInTheDocument();
	expect(screen.getAllByText('8').length).toBeGreaterThan(0);
});
