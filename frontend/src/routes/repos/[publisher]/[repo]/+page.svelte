<script lang="ts">
	import {
		buildSkillHref,
		firstDomain,
		formatWeeklyInstalls,
		registryLabels,
		severityTone
	} from '$lib/presenters';
	import type { RepoDetail } from '$lib/types';

	let { data } = $props<{ data: { repo: RepoDetail } }>();
</script>

<section class="hero hero--compact">
	<div class="hero-grid">
		<div>
			<p class="section-eyebrow">Repository drill-down</p>
			<h1>{data.repo.publisher}/{data.repo.repo}</h1>
			<p>
				This repo view rolls up the latest severity across every discovered skill in the repository
				without rescanning the full snapshot table on each request.
			</p>
			{#if data.repo.sourceUrl}
				<p class="table-subtext">
					Source:
					<a class="inline-link" href={data.repo.sourceUrl} target="_blank" rel="noreferrer">
						{data.repo.sourceUrl}
					</a>
				</p>
			{/if}
		</div>

		<div class="hero-panel stack">
			<div class="kpi-line">
				<span class="muted">Flagged skills</span>
				<strong>{data.repo.flaggedSkillCount}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Critical skills</span>
				<strong>{data.repo.criticalSkillCount}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Top severity</span>
				<strong>{data.repo.topSeverity}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Flagged installs</span>
				<strong>{formatWeeklyInstalls(data.repo.totalInstalls, '0')}</strong>
			</div>
		</div>
	</div>
</section>

<section class="table-card page-section">
	<div class="table-header">
		<div>
			<p class="table-label">Repository inventory</p>
			<h2>Skills in this repo</h2>
		</div>
	</div>

	{#if data.repo.skills.length > 0}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th>Skill</th>
						<th>Registries</th>
						<th>Total installs</th>
						<th>Severity</th>
						<th>Top domain</th>
					</tr>
				</thead>
				<tbody>
					{#each data.repo.skills as skill}
						<tr>
							<td>
								<a class="inline-link" href={buildSkillHref(skill)}>
									{skill.publisher}/{skill.repo}/{skill.skillSlug}
								</a>
								<p class="table-subtext">{skill.title}</p>
							</td>
							<td>
								{#if registryLabels(skill).length > 0}
									<div class="token-list">
										{#each registryLabels(skill) as source}
											<span class="token">{source}</span>
										{/each}
									</div>
								{:else}
									<span class="table-subtext">Unlisted</span>
								{/if}
							</td>
							<td class="mono">
								{formatWeeklyInstalls(skill.currentTotalInstalls ?? skill.currentWeeklyInstalls)}
							</td>
							<td>
								<span class="badge" data-level={severityTone(skill.latestSnapshot.riskReport.severity)}>
									{skill.latestSnapshot.riskReport.severity}
								</span>
							</td>
							<td class="mono">{firstDomain(skill.latestSnapshot.extractedDomains)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="empty-state">No skills have been indexed for this repository yet.</div>
	{/if}
</section>
