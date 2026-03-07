import type { PageLoad } from './$types';
import { loadOverview } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
	return await loadOverview(fetch);
};
