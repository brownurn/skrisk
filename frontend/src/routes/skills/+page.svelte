<script lang="ts">
	import {
		buildSkillHref,
		firstDomain,
		formatObservedAt,
		formatWeeklyInstalls,
		installTrendLabel,
		priorityTone,
		severityTone
	} from '$lib/presenters';
	import type { SeverityLevel, SkillSummary } from '$lib/types';

	let { data } = $props<{ data: { skills: SkillSummary[] } }>();

	type InstallBucket = 'all' | '0-9' | '10-99' | '100-999' | '1k-9.9k' | '10k+';
	type SortMode = 'priority' | 'installs';

	const severityOptions: Array<{ label: string; value: SeverityLevel | 'all' }> = [
		{ label: 'All severities', value: 'all' },
		{ label: 'Critical', value: 'critical' },
		{ label: 'High', value: 'high' },
		{ label: 'Medium', value: 'medium' },
		{ label: 'Low', value: 'low' },
		{ label: 'None', value: 'none' }
	];

	const installBucketOptions: Array<{ label: string; value: InstallBucket }> = [
		{ label: 'All install footprints', value: 'all' },
		{ label: '0-9 weekly installs', value: '0-9' },
		{ label: '10-99 weekly installs', value: '10-99' },
		{ label: '100-999 weekly installs', value: '100-999' },
		{ label: '1k-9.9k weekly installs', value: '1k-9.9k' },
		{ label: '10k+ weekly installs', value: '10k+' }
	];

	const sortOptions: Array<{ label: string; value: SortMode }> = [
		{ label: 'Priority', value: 'priority' },
		{ label: 'Weekly installs', value: 'installs' }
	];

	let query = $state('');
	let severityFilter = $state<SeverityLevel | 'all'>('all');
	let installBucketFilter = $state<InstallBucket>('all');
	let sortMode = $state<SortMode>('priority');

	const totalWeeklyInstalls = $derived(
		data.skills.reduce(
			(total: number, skill: SkillSummary) => total + (skill.currentWeeklyInstalls ?? 0),
			0
		)
	);

	function matchesInstallBucket(weeklyInstalls: number | null, bucket: InstallBucket): boolean {
		if (bucket === 'all') {
			return true;
		}

		if (weeklyInstalls === null) {
			return false;
		}

		switch (bucket) {
			case '0-9':
				return weeklyInstalls >= 0 && weeklyInstalls < 10;
			case '10-99':
				return weeklyInstalls >= 10 && weeklyInstalls < 100;
			case '100-999':
				return weeklyInstalls >= 100 && weeklyInstalls < 1_000;
			case '1k-9.9k':
				return weeklyInstalls >= 1_000 && weeklyInstalls < 10_000;
			case '10k+':
				return weeklyInstalls >= 10_000;
			default:
				return true;
		}
	}

	const filteredSkills = $derived.by(() => {
		const normalizedQuery = query.trim().toLowerCase();

		return [...data.skills]
			.filter((skill) => {
				if (severityFilter !== 'all' && skill.latestSnapshot.riskReport.severity !== severityFilter) {
					return false;
				}

				if (!matchesInstallBucket(skill.currentWeeklyInstalls, installBucketFilter)) {
					return false;
				}

				if (!normalizedQuery) {
					return true;
				}

				const haystack = [
					skill.publisher,
					skill.repo,
					skill.skillSlug,
					skill.title,
					String(skill.priorityScore),
					String(skill.currentWeeklyInstalls ?? ''),
					...skill.latestSnapshot.riskReport.categories,
					...skill.latestSnapshot.extractedDomains
				]
					.join(' ')
					.toLowerCase();

				return haystack.includes(normalizedQuery);
			})
			.sort((left, right) => {
				if (sortMode === 'installs') {
					return (
						(right.currentWeeklyInstalls ?? -1) - (left.currentWeeklyInstalls ?? -1) ||
						right.priorityScore - left.priorityScore
					);
				}

				return (
					right.priorityScore - left.priorityScore ||
					(right.currentWeeklyInstalls ?? -1) - (left.currentWeeklyInstalls ?? -1) ||
					right.latestSnapshot.riskReport.score - left.latestSnapshot.riskReport.score
				);
			});
	});
</script>

<section class="hero hero--compact">
	<div class="hero-grid">
		<div>
			<p class="section-eyebrow">Registry-wide analyst view</p>
			<h1>Skills registry</h1>
			<p>
				Prioritize the skills combining suspicious behavior with meaningful install reach.
				Filters stay local and keyboard-friendly for fast analyst triage.
			</p>
		</div>

		<div class="hero-panel stack">
			<div class="kpi-line">
				<span class="muted">Tracked skills</span>
				<strong>{data.skills.length}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Total weekly installs</span>
				<strong>{formatWeeklyInstalls(totalWeeklyInstalls)}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Priority 80+</span>
				<strong>{data.skills.filter((skill: SkillSummary) => skill.priorityScore >= 80).length}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">10k+ weekly</span>
				<strong>{data.skills.filter((skill: SkillSummary) => (skill.currentWeeklyInstalls ?? 0) >= 10_000).length}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Intel-backed</span>
				<strong>{data.skills.filter((skill: SkillSummary) => skill.latestSnapshot.riskReport.indicatorMatches.length > 0).length}</strong>
			</div>
		</div>
	</div>
</section>

<section class="table-card page-section">
	<div class="table-header">
		<div>
			<p class="table-label">Analyst filters</p>
			<h2>Evidence queue</h2>
		</div>
	</div>

	<div class="toolbar" role="search">
		<div class="field">
			<label for="skills-query">Search skills</label>
			<input
				id="skills-query"
				name="skills-query"
				aria-label="Search skills"
				type="search"
				bind:value={query}
				placeholder="publisher / repo / domain / category"
			/>
		</div>
		<div class="field">
			<label for="skills-severity">Severity</label>
			<select
				id="skills-severity"
				name="skills-severity"
				aria-label="Severity"
				bind:value={severityFilter}
			>
				{#each severityOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
		</div>
		<div class="field">
			<label for="skills-installs">Weekly installs</label>
			<select
				id="skills-installs"
				name="skills-installs"
				aria-label="Weekly installs"
				bind:value={installBucketFilter}
			>
				{#each installBucketOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
		</div>
		<div class="field">
			<label for="skills-sort">Sort by</label>
			<select id="skills-sort" name="skills-sort" aria-label="Sort by" bind:value={sortMode}>
				{#each sortOptions as option}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
		</div>
	</div>

	{#if filteredSkills.length > 0}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th>Skill</th>
						<th>Priority</th>
						<th>Weekly Installs</th>
						<th>Severity</th>
						<th>Confidence</th>
						<th>Signals</th>
						<th>Indicators</th>
						<th>Top domain</th>
					</tr>
				</thead>
				<tbody>
					{#each filteredSkills as skill}
						<tr>
							<td>
								<a class="inline-link" href={buildSkillHref(skill)}>
									{skill.publisher}/{skill.repo}/{skill.skillSlug}
								</a>
								<p class="table-subtext">{skill.title}</p>
							</td>
							<td>
								<span class="badge" data-level={priorityTone(skill.priorityScore)}>
									{skill.priorityScore}
								</span>
								<p class="table-subtext">impact {skill.impactScore}</p>
							</td>
							<td>
								<strong class="mono">{formatWeeklyInstalls(skill.currentWeeklyInstalls)}</strong>
								<p class="table-subtext">
									{installTrendLabel(skill.weeklyInstallsDelta)} · {formatObservedAt(skill.currentWeeklyInstallsObservedAt)}
								</p>
							</td>
							<td>
								<span class="badge" data-level={severityTone(skill.latestSnapshot.riskReport.severity)}>
									{skill.latestSnapshot.riskReport.severity}
								</span>
							</td>
							<td>{skill.latestSnapshot.riskReport.confidence ?? 'unscored'}</td>
							<td class="mono">
								b {skill.latestSnapshot.riskReport.behaviorScore ?? 0} / i {skill.latestSnapshot.riskReport.intelScore ?? 0}
								/ c {skill.latestSnapshot.riskReport.changeScore ?? 0}
							</td>
							<td>{skill.latestSnapshot.riskReport.indicatorMatches.length}</td>
							<td class="mono">{firstDomain(skill.latestSnapshot.extractedDomains)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="empty-state">No skills match the current filter set.</div>
	{/if}
</section>
