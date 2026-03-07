import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import IndicatorDetailPage from './+page.svelte';

test('renders indicator observations and linked skills', () => {
	render(IndicatorDetailPage, {
		data: {
			indicator: {
				indicator: {
					id: 5,
					indicatorType: 'domain',
					indicatorValue: 'drop.example',
					normalizedValue: 'drop.example'
				},
				observations: [
					{
						id: 1,
						sourceProvider: 'abusech',
						sourceFeed: 'urlhaus',
						classification: 'malware_download',
						confidenceLabel: 'high',
						summary: 'Observed serving malware payloads'
					}
				],
				enrichments: [],
				linkedSkills: [
					{
						publisher: 'melurna',
						repo: 'skill-pack',
						skillSlug: 'network-probe',
						snapshotId: 14,
						versionLabel: 'v1.3.0',
						sourcePath: 'probe.sh',
						extractionKind: 'url'
					}
				]
			}
		}
	});

	expect(screen.getByRole('heading', { name: 'drop.example' })).toBeInTheDocument();
	expect(screen.getByRole('heading', { name: 'Linked skills' })).toBeInTheDocument();
	expect(screen.getByText('malware_download')).toBeInTheDocument();
});
