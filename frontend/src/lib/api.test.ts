import { expect, test } from 'vitest';

import { loadSkillDetail, loadSkills } from './api';

test('loadSkills requests priority ordering and normalizes install telemetry', async () => {
	let requestedUrl = '';

	const fetcher = (async (input: RequestInfo | URL) => {
		requestedUrl = String(input);
		return new Response(
			JSON.stringify([
				{
					publisher: 'tul-sh',
					repo: 'skills',
					skill_slug: 'agent-tools',
					title: 'Agent Tools',
					current_weekly_installs: 12_000,
					current_weekly_installs_observed_at: '2026-03-07T08:00:00+00:00',
					peak_weekly_installs: 18_000,
					weekly_installs_delta: 3_000,
					impact_score: 90,
					priority_score: 94,
					latest_snapshot: {
						id: 14,
						version_label: 'v1.3.0',
						folder_hash: 'abc123',
						referenced_files: ['SKILL.md'],
						extracted_domains: ['drop.example'],
						risk_report: {
							severity: 'high',
							score: 88,
							behavior_score: 55,
							intel_score: 22,
							change_score: 11,
							confidence: 'likely',
							categories: ['exfiltration'],
							domains: ['drop.example'],
							findings: [],
							indicator_matches: []
						}
					}
				}
			]),
			{
			status: 200,
			headers: { 'content-type': 'application/json' }
			}
		);
	}) as typeof fetch;

	const skills = await loadSkills(fetcher);

	expect(requestedUrl.endsWith('/api/skills?limit=0&sort=priority')).toBe(true);
	expect(skills[0]).toMatchObject({
		publisher: 'tul-sh',
		repo: 'skills',
		skillSlug: 'agent-tools',
		currentWeeklyInstalls: 12_000,
		currentWeeklyInstallsObservedAt: '2026-03-07T08:00:00+00:00',
		peakWeeklyInstalls: 18_000,
		weeklyInstallsDelta: 3_000,
		impactScore: 90,
		priorityScore: 94
	});
});

test('loadSkillDetail normalizes install history rows', async () => {
	const fetcher = (async () => {
		return new Response(
			JSON.stringify({
				publisher: 'tul-sh',
				repo: 'skills',
				skill_slug: 'agent-tools',
				title: 'Agent Tools',
				relative_path: 'skills/agent-tools',
				registry_url: 'https://skills.sh/tul-sh/skills/agent-tools',
				current_weekly_installs: 1_500,
				current_weekly_installs_observed_at: '2026-03-07T08:00:00+00:00',
				peak_weekly_installs: 2_000,
				weekly_installs_delta: 500,
				impact_score: 60,
				priority_score: 94,
				install_history: [
					{
						id: 1,
						skill_id: 3,
						registry_sync_run_id: 10,
						repo_snapshot_id: null,
						observed_at: '2026-03-01T08:00:00+00:00',
						weekly_installs: 1_000,
						registry_rank: 4,
						observation_kind: 'directory_fetch',
						raw_payload: { source: 'directory' }
					},
					{
						id: 2,
						skill_id: 3,
						registry_sync_run_id: 10,
						repo_snapshot_id: 14,
						observed_at: '2026-03-07T08:00:00+00:00',
						weekly_installs: 1_500,
						registry_rank: 4,
						observation_kind: 'scan_attribution',
						raw_payload: { source: 'scan' }
					}
				],
				external_verdicts: [],
				latest_snapshot: {
					id: 14,
					version_label: 'v1.3.0',
					folder_hash: 'abc123',
					referenced_files: ['SKILL.md'],
					extracted_domains: ['drop.example'],
					risk_report: {
						severity: 'high',
						score: 88,
						behavior_score: 55,
						intel_score: 22,
						change_score: 11,
						confidence: 'likely',
						categories: ['exfiltration'],
						domains: ['drop.example'],
						findings: [],
						indicator_matches: []
					},
					indicator_links: []
				}
			}),
			{
				status: 200,
				headers: { 'content-type': 'application/json' }
			}
		);
	}) as typeof fetch;

	const skill = await loadSkillDetail(fetcher, 'tul-sh', 'skills', 'agent-tools');

	expect(skill).toMatchObject({
		currentWeeklyInstalls: 1_500,
		peakWeeklyInstalls: 2_000,
		weeklyInstallsDelta: 500,
		impactScore: 60,
		priorityScore: 94
	});
	expect(skill.installHistory).toEqual([
		{
			id: 1,
			skillId: 3,
			registrySyncRunId: 10,
			repoSnapshotId: null,
			observedAt: '2026-03-01T08:00:00+00:00',
			weeklyInstalls: 1_000,
			registryRank: 4,
			observationKind: 'directory_fetch',
			rawPayload: { source: 'directory' }
		},
		{
			id: 2,
			skillId: 3,
			registrySyncRunId: 10,
			repoSnapshotId: 14,
			observedAt: '2026-03-07T08:00:00+00:00',
			weeklyInstalls: 1_500,
			registryRank: 4,
			observationKind: 'scan_attribution',
			rawPayload: { source: 'scan' }
		}
	]);
});
