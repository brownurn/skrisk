import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { within } from '@testing-library/dom';
import { expect, test } from 'vitest';
import SkillsPage from './+page.svelte';

test('renders weekly installs and priority columns in priority order', () => {
	render(SkillsPage, {
		data: {
			skills: [
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
					}
				},
				{
					publisher: 'melurna',
					repo: 'skill-pack',
					skillSlug: 'network-probe',
					title: 'Network Probe',
					currentWeeklyInstalls: 24,
					currentWeeklyInstallsObservedAt: '2026-03-07T08:00:00+00:00',
					peakWeeklyInstalls: 100,
					weeklyInstallsDelta: -10,
					impactScore: 15,
					priorityScore: 32,
					latestSnapshot: {
						id: 22,
						versionLabel: 'v1.3.0',
						folderHash: 'def456',
						referencedFiles: ['SKILL.md'],
						extractedDomains: ['low.example'],
						riskReport: {
							severity: 'critical',
							score: 88,
							behaviorScore: 55,
							intelScore: 22,
							changeScore: 11,
							confidence: 'likely',
							categories: ['exfiltration'],
							domains: ['low.example'],
							findings: [],
							indicatorMatches: []
						}
					}
				}
			]
		}
	});

	expect(screen.getByRole('heading', { name: 'Skills registry' })).toBeInTheDocument();
	expect(screen.getByRole('columnheader', { name: /weekly installs/i })).toBeInTheDocument();
	expect(screen.getByRole('columnheader', { name: /priority/i })).toBeInTheDocument();
	expect(screen.getByText('12.0k')).toBeInTheDocument();
	expect(screen.getByText('94')).toBeInTheDocument();

	const rows = screen.getAllByRole('row');
	expect(within(rows[1]).getByRole('link', { name: 'tul-sh/skills/agent-tools' })).toBeInTheDocument();
});
