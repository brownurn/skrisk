import { expect, test } from 'vitest';

import { loadSkills } from './api';

test('loadSkills requests the full registry from the backend', async () => {
	let requestedUrl = '';

	const fetcher = (async (input: RequestInfo | URL) => {
		requestedUrl = String(input);
		return new Response(JSON.stringify([]), {
			status: 200,
			headers: { 'content-type': 'application/json' }
		});
	}) as typeof fetch;

	await loadSkills(fetcher);

	expect(requestedUrl.endsWith('/api/skills?limit=0')).toBe(true);
});
