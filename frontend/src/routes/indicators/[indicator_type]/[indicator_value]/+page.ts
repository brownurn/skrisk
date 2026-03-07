import type { PageLoad } from './$types';
import { loadIndicatorDetail } from '$lib/api';

export const load: PageLoad = async ({ fetch, params }) => {
	return {
		indicator: await loadIndicatorDetail(fetch, params.indicator_type, params.indicator_value)
	};
};
