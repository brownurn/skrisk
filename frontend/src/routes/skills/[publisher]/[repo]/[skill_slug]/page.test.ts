import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import SkillDetailPage from './+page.svelte';

test('renders install telemetry and history alongside skill evidence', () => {
	render(SkillDetailPage, {
		data: {
			skill: {
				publisher: 'melurna',
				repo: 'skill-pack',
				skillSlug: 'network-probe',
				title: 'Network Probe',
				relativePath: 'skills/network-probe',
				registryUrl: 'https://skills.sh/melurna/skill-pack/network-probe',
				currentWeeklyInstalls: 1_500,
				currentWeeklyInstallsObservedAt: '2026-03-07T08:00:00+00:00',
				peakWeeklyInstalls: 2_000,
				weeklyInstallsDelta: 500,
				impactScore: 60,
				priorityScore: 94,
				installHistory: [
					{
						id: 1,
						skillId: 3,
						registrySyncRunId: 10,
						repoSnapshotId: null,
						observedAt: '2026-03-01T08:00:00+00:00',
						weeklyInstalls: 1_000,
						registryRank: 4,
						observationKind: 'directory_fetch',
						rawPayload: { source: 'directory' }
					},
					{
						id: 2,
						skillId: 3,
						registrySyncRunId: 10,
						repoSnapshotId: 14,
						observedAt: '2026-03-07T08:00:00+00:00',
						weeklyInstalls: 1_500,
						registryRank: 4,
						observationKind: 'scan_attribution',
						rawPayload: { source: 'scan' }
					}
				],
				externalVerdicts: [],
				latestSnapshot: {
					id: 14,
					versionLabel: 'v1.3.0',
					folderHash: 'abc123',
					referencedFiles: ['SKILL.md', 'probe.sh'],
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
						findings: [
							{
								path: 'probe.sh',
								category: 'network_egress',
								severity: 'high',
								evidence: 'Posts local files to a remote endpoint'
							}
						],
						indicatorMatches: []
					},
					indicatorLinks: [
						{
							indicatorId: 7,
							indicatorType: 'domain',
							indicatorValue: 'drop.example',
							sourcePath: 'probe.sh',
							extractionKind: 'url',
							rawValue: 'https://drop.example/upload',
							isNewInSnapshot: true
						}
					]
				}
			}
		}
	});

	expect(screen.getByRole('heading', { name: 'Network Probe' })).toBeInTheDocument();
	expect(screen.getByText('Latest Weekly Installs')).toBeInTheDocument();
	expect(screen.getByText('Peak Weekly Installs')).toBeInTheDocument();
	expect(screen.getByText('Install Delta')).toBeInTheDocument();
	expect(screen.getByText('Priority')).toBeInTheDocument();
	expect(screen.getByText('Impact')).toBeInTheDocument();
	expect(screen.getAllByText('1.5k').length).toBeGreaterThan(0);
	expect(screen.getAllByText('2.0k').length).toBeGreaterThan(0);
	expect(screen.getByText('+500')).toBeInTheDocument();
	expect(screen.getByRole('heading', { name: 'Install history' })).toBeInTheDocument();
	expect(screen.getByText('Scan attribution')).toBeInTheDocument();
	expect(screen.getByRole('heading', { name: 'Behavior findings' })).toBeInTheDocument();
	expect(screen.getByRole('link', { name: 'drop.example' })).toBeInTheDocument();
});
