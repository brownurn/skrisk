<script lang="ts">
	import { buildSkillHref, firstDomain, severityRank, severityTone } from '$lib/presenters';
	import type { SeverityLevel, SkillSummary } from '$lib/types';

	let { data } = $props<{ data: { skills: SkillSummary[] } }>();

	const severityOptions: Array<{ label: string; value: SeverityLevel | 'all' }> = [
		{ label: 'All severities', value: 'all' },
		{ label: 'Critical', value: 'critical' },
		{ label: 'High', value: 'high' },
		{ label: 'Medium', value: 'medium' },
		{ label: 'Low', value: 'low' },
		{ label: 'None', value: 'none' }
	];

	let query = $state('');
	let severityFilter = $state<SeverityLevel | 'all'>('all');

	const filteredSkills = $derived.by(() => {
		const normalizedQuery = query.trim().toLowerCase();

		return [...data.skills]
			.filter((skill) => {
				if (severityFilter !== 'all' && skill.latestSnapshot.riskReport.severity !== severityFilter) {
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
					...skill.latestSnapshot.riskReport.categories,
					...skill.latestSnapshot.extractedDomains
				]
					.join(' ')
					.toLowerCase();

				return haystack.includes(normalizedQuery);
			})
			.sort((left, right) => {
				const severityDelta =
					severityRank(right.latestSnapshot.riskReport.severity) -
					severityRank(left.latestSnapshot.riskReport.severity);

				if (severityDelta !== 0) {
					return severityDelta;
				}

				return right.latestSnapshot.riskReport.score - left.latestSnapshot.riskReport.score;
			});
	});
</script>

<section class="hero hero--compact">
	<div class="hero-grid">
		<div>
			<p class="section-eyebrow">Registry-wide analyst view</p>
			<h1>Skills registry</h1>
			<p>
				Prioritize the skills introducing egress, obfuscation, suspicious infrastructure, or
				other capability drift. Filters stay local and keyboard-friendly for quick triage.
			</p>
		</div>

		<div class="hero-panel stack">
			<div class="kpi-line">
				<span class="muted">Tracked skills</span>
				<strong>{data.skills.length}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Critical</span>
				<strong>{data.skills.filter((skill: SkillSummary) => skill.latestSnapshot.riskReport.severity === 'critical').length}</strong>
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
				type="search"
				bind:value={query}
				placeholder="publisher / repo / domain / category"
			/>
		</div>
		<div class="field">
			<label for="skills-severity">Severity</label>
			<select id="skills-severity" name="skills-severity" bind:value={severityFilter}>
				{#each severityOptions as option}
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
