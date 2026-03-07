import type { PageLoad } from './$types';
import { loadSkillDetail } from '$lib/api';

export const load: PageLoad = async ({ fetch, params }) => {
	return {
		skill: await loadSkillDetail(fetch, params.publisher, params.repo, params.skill_slug)
	};
};
