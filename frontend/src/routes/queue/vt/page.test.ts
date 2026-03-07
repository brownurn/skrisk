import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import VTQueuePage from './+page.svelte';

test('renders the virustotal queue status', () => {
	render(VTQueuePage, {
		data: {
			queue: {
				dailyBudget: 490,
				dailyBudgetUsed: 37,
				dailyBudgetRemaining: 453,
				queueItems: [
					{
						id: 9,
						indicatorId: 5,
						indicatorType: 'domain',
						indicatorValue: 'drop.example',
						priority: 90,
						reason: 'critical skill introduced new egress indicator',
						status: 'queued',
						attemptCount: 0
					}
				]
			}
		}
	});

	expect(screen.getByRole('heading', { name: 'VirusTotal queue' })).toBeInTheDocument();
	expect(screen.getByText('drop.example')).toBeInTheDocument();
});
