import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import SkillDetailPage from './+page.svelte';

test('renders skill evidence sections', () => {
	render(SkillDetailPage, {
		data: {
			skill: {
				publisher: 'melurna',
				repo: 'skill-pack',
				skillSlug: 'network-probe',
				title: 'Network Probe',
				relativePath: 'skills/network-probe',
				registryUrl: 'https://skills.sh/melurna/skill-pack/network-probe',
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
	expect(screen.getByRole('heading', { name: 'Behavior findings' })).toBeInTheDocument();
	expect(screen.getByRole('link', { name: 'drop.example' })).toBeInTheDocument();
});
