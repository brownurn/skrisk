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
				currentWeeklyInstalls: 1_800,
				currentWeeklyInstallsObservedAt: '2026-03-07T08:00:00+00:00',
				currentTotalInstalls: 1_800,
				currentTotalInstallsObservedAt: '2026-03-07T08:00:00+00:00',
				peakWeeklyInstalls: 2_000,
				weeklyInstallsDelta: 500,
				impactScore: 60,
				priorityScore: 94,
				sourceCount: 2,
				sources: ['skills.sh', 'skillsmp'],
				installBreakdown: [
					{
						sourceName: 'skills.sh',
						weeklyInstalls: 1_500,
						sourceUrl: 'https://skills.sh/melurna/skill-pack/network-probe',
						registryRank: 4
					},
					{
						sourceName: 'skillsmp',
						weeklyInstalls: 300,
						sourceUrl: 'https://skillsmp.com/skills/melurna-skill-pack-network-probe-skill-md',
						registryRank: null
					}
				],
				sourceEntries: [
					{
						id: 1,
						registrySourceId: 11,
						sourceName: 'skills.sh',
						sourceBaseUrl: 'https://skills.sh',
						sourceUrl: 'https://skills.sh/melurna/skill-pack/network-probe',
						sourceNativeId: null,
						currentRegistrySyncRunId: null,
						currentRegistrySyncObservedAt: null,
						view: 'all-time',
						weeklyInstalls: 1_500,
						registryRank: 4,
						firstSeenAt: '2026-03-01T08:00:00+00:00',
						lastSeenAt: '2026-03-07T08:00:00+00:00',
						rawPayload: { source: 'skills.sh' }
					},
					{
						id: 2,
						registrySourceId: 12,
						sourceName: 'skillsmp',
						sourceBaseUrl: 'https://skillsmp.com',
						sourceUrl:
							'https://skillsmp.com/skills/melurna-skill-pack-network-probe-skill-md',
						sourceNativeId: 'melurna-skill-pack-network-probe-skill-md',
						currentRegistrySyncRunId: null,
						currentRegistrySyncObservedAt: null,
						view: 'all-time',
						weeklyInstalls: 300,
						registryRank: null,
						firstSeenAt: '2026-03-02T08:00:00+00:00',
						lastSeenAt: '2026-03-07T08:00:00+00:00',
						rawPayload: { source: 'skillsmp' }
					}
				],
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
	expect(screen.getByText('Total Installs')).toBeInTheDocument();
	expect(screen.getByText('Peak Weekly Installs')).toBeInTheDocument();
	expect(screen.getByText('Install Delta')).toBeInTheDocument();
	expect(screen.getByText('Priority')).toBeInTheDocument();
	expect(screen.getByText('Impact')).toBeInTheDocument();
	expect(screen.getAllByText('1.8k').length).toBeGreaterThan(0);
	expect(screen.getAllByText('2.0k').length).toBeGreaterThan(0);
	expect(screen.getByText('+500')).toBeInTheDocument();
	expect(screen.getAllByRole('heading', { name: 'Seen in registries' }).length).toBeGreaterThan(0);
	expect(screen.getAllByText('skills.sh').length).toBeGreaterThan(0);
	expect(screen.getAllByText('skillsmp').length).toBeGreaterThan(0);
	expect(screen.getByText('300')).toBeInTheDocument();
	expect(screen.getByRole('heading', { name: 'Install history' })).toBeInTheDocument();
	expect(screen.getByText('Scan attribution')).toBeInTheDocument();
	expect(screen.getByRole('heading', { name: 'Why this skill is flagged' })).toBeInTheDocument();
	expect(screen.getByText(/Hard evidence/)).toBeInTheDocument();
	expect(screen.getAllByText(/Posts local files to a remote endpoint/).length).toBeGreaterThan(0);
	expect(screen.getByRole('heading', { name: 'Behavior findings' })).toBeInTheDocument();
	expect(screen.getAllByRole('link', { name: 'drop.example' }).length).toBeGreaterThan(0);
});

test('renders a no-hard-evidence verdict when the latest snapshot is clean', () => {
	render(SkillDetailPage, {
		data: {
			skill: {
				publisher: 'anthropics',
				repo: 'skills',
				skillSlug: 'skill-creator',
				title: 'Skill Creator',
				relativePath: 'skills/skill-creator',
				registryUrl: 'https://skills.sh/anthropics/skills/skill-creator',
				currentWeeklyInstalls: 451_538,
				currentWeeklyInstallsObservedAt: '2026-03-10T20:00:00+00:00',
				currentTotalInstalls: 451_538,
				currentTotalInstallsObservedAt: '2026-03-10T20:00:00+00:00',
				peakWeeklyInstalls: 451_538,
				weeklyInstallsDelta: 0,
				impactScore: 90,
				priorityScore: 45,
				sourceCount: 1,
				sources: ['skills.sh'],
				installBreakdown: [
					{
						sourceName: 'skills.sh',
						weeklyInstalls: 451_538,
						sourceUrl: 'https://skills.sh/anthropics/skills/skill-creator',
						registryRank: 1
					}
				],
				sourceEntries: [],
				installHistory: [],
				externalVerdicts: [],
				latestSnapshot: {
					id: 510215,
					versionLabel: 'b0cbd3d',
					folderHash: 'safe123',
					referencedFiles: ['SKILL.md', 'scripts/run_eval.py'],
					extractedDomains: [
						'apache.org',
						'claude.ai',
						'fonts.googleapis.com',
						'fonts.gstatic.com',
						'localhost'
					],
					riskReport: {
						severity: 'none',
						score: 0,
						behaviorScore: 0,
						intelScore: 0,
						changeScore: 0,
						confidence: 'suspected',
						categories: [],
						domains: [
							'apache.org',
							'claude.ai',
							'fonts.googleapis.com',
							'fonts.gstatic.com',
							'localhost'
						],
						findings: [],
						indicatorMatches: []
					},
					indicatorLinks: [
						{
							indicatorId: 1,
							indicatorType: 'domain',
							indicatorValue: 'claude.ai',
							sourcePath: 'scripts/run_eval.py',
							extractionKind: 'inline-url',
							rawValue: 'https://claude.ai',
							isNewInSnapshot: false
						}
					]
				}
			}
		}
	});

	expect(screen.getAllByRole('heading', { name: 'Why this skill is flagged' }).length).toBeGreaterThan(0);
	expect(
		screen.getByText(/No hard evidence of exfiltration, malware delivery, or covert outbound infrastructure/)
	).toBeInTheDocument();
	expect(screen.getByText(/Decoded or reconstructed text alone is not treated as malicious/)).toBeInTheDocument();
});
