import type { PageLoad } from './$types';
import { loadVTQueue } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
	return {
		queue: await loadVTQueue(fetch)
	};
};
