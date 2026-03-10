import type { PageLoad } from './$types';
import { loadRepoDetail } from '$lib/api';

export const load: PageLoad = async ({ fetch, params }) => {
	return {
		repo: await loadRepoDetail(fetch, params.publisher, params.repo)
	};
};
