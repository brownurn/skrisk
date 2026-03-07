import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import SkillsPage from './+page.svelte';

test('renders the skills analyst list', () => {
	render(SkillsPage, {
		data: {
			skills: [
				{
					publisher: 'melurna',
					repo: 'skill-pack',
					skillSlug: 'network-probe',
					title: 'Network Probe',
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
							indicatorMatches: [{ indicatorType: 'domain', indicatorValue: 'drop.example', observations: [] }]
						}
					}
				}
			]
		}
	});

	expect(screen.getByRole('heading', { name: 'Skills registry' })).toBeInTheDocument();
	expect(screen.getByText('melurna/skill-pack/network-probe')).toBeInTheDocument();
});
