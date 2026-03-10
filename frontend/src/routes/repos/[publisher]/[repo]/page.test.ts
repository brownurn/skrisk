import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import RepoPage from './+page.svelte';

test('renders repo detail with flagged and clear skills', () => {
	render(RepoPage, {
		data: {
			repo: {
				publisher: 'ypyt1',
				repo: 'all-skills',
				sourceUrl: 'https://github.com/ypyt1/all-skills',
				flaggedSkillCount: 1,
				criticalSkillCount: 1,
				topSeverity: 'critical',
				topRiskScore: 92,
				totalInstalls: 5100,
				skills: [
					{
						publisher: 'ypyt1',
						repo: 'all-skills',
						skillSlug: 'dangerous-helper',
						title: 'dangerous-helper',
						currentWeeklyInstalls: 5000,
						currentWeeklyInstallsObservedAt: '2026-03-10T02:00:00+00:00',
						currentTotalInstalls: 5000,
						currentTotalInstallsObservedAt: '2026-03-10T02:00:00+00:00',
						peakWeeklyInstalls: 5000,
						weeklyInstallsDelta: 1200,
						impactScore: 90,
						priorityScore: 98,
						sourceCount: 1,
						sources: ['skills.sh'],
						installBreakdown: [
							{
								sourceName: 'skills.sh',
								weeklyInstalls: 5000,
								sourceUrl: 'https://skills.sh/ypyt1/all-skills/dangerous-helper',
								registryRank: 1
							}
						],
						latestSnapshot: {
							id: 14,
							versionLabel: 'main@abc123',
							folderHash: 'abc123',
							referencedFiles: ['SKILL.md'],
							extractedDomains: ['drop.example'],
							riskReport: {
								severity: 'critical',
								score: 92,
								behaviorScore: 60,
								intelScore: 20,
								changeScore: 12,
								confidence: 'confirmed',
								categories: ['exfiltration'],
								domains: ['drop.example'],
								findings: [],
								indicatorMatches: []
							}
						}
					},
					{
						publisher: 'ypyt1',
						repo: 'all-skills',
						skillSlug: 'guide-only',
						title: 'guide-only',
						currentWeeklyInstalls: 100,
						currentWeeklyInstallsObservedAt: '2026-03-10T02:00:00+00:00',
						currentTotalInstalls: 100,
						currentTotalInstallsObservedAt: '2026-03-10T02:00:00+00:00',
						peakWeeklyInstalls: 100,
						weeklyInstallsDelta: 0,
						impactScore: 30,
						priorityScore: 12,
						sourceCount: 1,
						sources: ['skills.sh'],
						installBreakdown: [
							{
								sourceName: 'skills.sh',
								weeklyInstalls: 100,
								sourceUrl: 'https://skills.sh/ypyt1/all-skills/guide-only',
								registryRank: 2
							}
						],
						latestSnapshot: {
							id: 15,
							versionLabel: 'main@abc123',
							folderHash: 'def456',
							referencedFiles: ['SKILL.md'],
							extractedDomains: [],
							riskReport: {
								severity: 'none',
								score: 0,
								behaviorScore: 0,
								intelScore: 0,
								changeScore: 0,
								confidence: 'likely',
								categories: [],
								domains: [],
								findings: [],
								indicatorMatches: []
							}
						}
					}
				]
			}
		}
	});

	expect(screen.getByRole('heading', { name: 'ypyt1/all-skills' })).toBeInTheDocument();
	expect(screen.getByText('Flagged skills')).toBeInTheDocument();
	expect(screen.getByText('Critical skills')).toBeInTheDocument();
	expect(screen.getByRole('link', { name: 'ypyt1/all-skills/dangerous-helper' })).toHaveAttribute(
		'href',
		'/skills/ypyt1/all-skills/dangerous-helper'
	);
	expect(screen.getByText('guide-only')).toBeInTheDocument();
});
