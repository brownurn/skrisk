import type { PageLoad } from './$types';
import { loadSkills } from '$lib/api';

export const load: PageLoad = async ({ fetch }) => {
	return {
		skills: await loadSkills(fetch)
	};
};
