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
			criticalSkills: [],
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
	expect(screen.getAllByText('8').length).toBeGreaterThan(0);
});
