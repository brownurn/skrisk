import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { within } from '@testing-library/dom';
import { expect, test } from 'vitest';
import SkillsPage from './+page.svelte';

test('renders weekly installs and priority columns in priority order', () => {
	const { container } = render(SkillsPage, {
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
					currentWeeklyInstalls: 999,
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
	expect(screen.getByText('Total weekly installs')).toBeInTheDocument();
	expect(screen.getByText('13.0k')).toBeInTheDocument();
	expect(screen.getByRole('columnheader', { name: /weekly installs/i })).toBeInTheDocument();
	expect(screen.getByRole('columnheader', { name: /priority/i })).toBeInTheDocument();
	expect(screen.getByText('12.0k')).toBeInTheDocument();
	expect(screen.getByText('94')).toBeInTheDocument();

	const rows = within(container).getAllByRole('row');
	expect(within(rows[1]).getByRole('link', { name: 'tul-sh/skills/agent-tools' })).toBeInTheDocument();
});

test('lets analysts switch the skills list to installs ordering', async () => {
	const { container } = render(SkillsPage, {
		data: {
			skills: [
				{
					publisher: 'priority',
					repo: 'pack',
					skillSlug: 'triage-first',
					title: 'Triage First',
					currentWeeklyInstalls: 120,
					currentWeeklyInstallsObservedAt: '2026-03-07T08:00:00+00:00',
					peakWeeklyInstalls: 200,
					weeklyInstallsDelta: 20,
					impactScore: 30,
					priorityScore: 95,
					latestSnapshot: {
						id: 11,
						versionLabel: 'v1.0.0',
						folderHash: 'aaa111',
						referencedFiles: ['SKILL.md'],
						extractedDomains: ['priority.example'],
						riskReport: {
							severity: 'critical',
							score: 90,
							behaviorScore: 55,
							intelScore: 22,
							changeScore: 11,
							confidence: 'likely',
							categories: ['exfiltration'],
							domains: ['priority.example'],
							findings: [],
							indicatorMatches: []
						}
					}
				},
				{
					publisher: 'installs',
					repo: 'pack',
					skillSlug: 'reach-first',
					title: 'Reach First',
					currentWeeklyInstalls: 24_000,
					currentWeeklyInstallsObservedAt: '2026-03-07T08:00:00+00:00',
					peakWeeklyInstalls: 24_000,
					weeklyInstallsDelta: 6_000,
					impactScore: 90,
					priorityScore: 60,
					latestSnapshot: {
						id: 12,
						versionLabel: 'v1.0.0',
						folderHash: 'bbb222',
						referencedFiles: ['SKILL.md'],
						extractedDomains: ['installs.example'],
						riskReport: {
							severity: 'medium',
							score: 50,
							behaviorScore: 25,
							intelScore: 15,
							changeScore: 10,
							confidence: 'likely',
							categories: ['network'],
							domains: ['installs.example'],
							findings: [],
							indicatorMatches: []
						}
					}
				}
			]
		}
	});

	expect(within(within(container).getAllByRole('row')[1]).getByRole('link', { name: 'priority/pack/triage-first' })).toBeInTheDocument();

	await fireEvent.change(within(container).getByRole('combobox', { name: /sort by/i }), {
		target: { value: 'installs' }
	});

	expect(within(within(container).getAllByRole('row')[1]).getByRole('link', { name: 'installs/pack/reach-first' })).toBeInTheDocument();
	expect(within(container).getByText('24.0k')).toBeInTheDocument();
});
