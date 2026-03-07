<script lang="ts">
	import { buildSkillHref, formatOptional } from '$lib/presenters';
	import type { IndicatorDetail, LinkedSkill } from '$lib/types';

	let { data } = $props<{ data: { indicator: IndicatorDetail } }>();

	function skillHref(skill: LinkedSkill): string {
		return buildSkillHref(skill);
	}
</script>

<section class="hero hero--compact">
	<div class="hero-grid">
		<div>
			<p class="section-eyebrow">Indicator intelligence dossier</p>
			<h1>{data.indicator.indicator.indicatorValue}</h1>
			<p class="hero-coordinate mono">{data.indicator.indicator.indicatorType}</p>
			<p>
				Correlate feed sightings, enrichment cache entries, and the skills currently referencing
				this indicator.
			</p>
		</div>

		<div class="hero-panel stack">
			<div class="kpi-line">
				<span class="muted">Observations</span>
				<strong>{data.indicator.observations.length}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Enrichments</span>
				<strong>{data.indicator.enrichments.length}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Linked skills</span>
				<strong>{data.indicator.linkedSkills.length}</strong>
			</div>
		</div>
	</div>
</section>

<section class="panel-grid">
	<div class="table-card">
		<div class="table-header">
			<div>
				<p class="table-label">Provider sightings</p>
				<h2>Observations</h2>
			</div>
		</div>

		{#if data.indicator.observations.length > 0}
			<div class="table-wrap">
				<table>
					<thead>
						<tr>
							<th>Provider</th>
							<th>Feed</th>
							<th>Classification</th>
							<th>Confidence</th>
							<th>Summary</th>
						</tr>
					</thead>
					<tbody>
						{#each data.indicator.observations as observation}
							<tr>
								<td>{formatOptional(observation.sourceProvider)}</td>
								<td>{formatOptional(observation.sourceFeed)}</td>
								<td>{formatOptional(observation.classification)}</td>
								<td>{formatOptional(observation.confidenceLabel)}</td>
								<td>{formatOptional(observation.summary)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{:else}
			<div class="empty-state">No provider observations are stored for this indicator yet.</div>
		{/if}
	</div>

	<div class="panel stack">
		<div>
			<p class="table-label">Enrichment cache</p>
			<h2>Provider enrichments</h2>
		</div>

		{#if data.indicator.enrichments.length > 0}
			{#each data.indicator.enrichments as enrichment}
				<div class="definition-card">
					<h3>{enrichment.provider}</h3>
					<p class="mono">{enrichment.lookupKey}</p>
					<p class="muted">{enrichment.status}</p>
					<p>{formatOptional(enrichment.summary)}</p>
					{#if enrichment.archiveRelativePath}
						<p class="table-subtext mono">{enrichment.archiveRelativePath}</p>
					{/if}
				</div>
			{/each}
		{:else}
			<div class="empty-state">No VT or partner enrichment is cached for this indicator yet.</div>
		{/if}
	</div>
</section>

<section class="table-card page-section">
	<div class="table-header">
		<div>
			<p class="table-label">Cross-skill reuse</p>
			<h2>Linked skills</h2>
		</div>
	</div>

	{#if data.indicator.linkedSkills.length > 0}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th>Skill</th>
						<th>Version</th>
						<th>Extraction</th>
						<th>Source path</th>
					</tr>
				</thead>
				<tbody>
					{#each data.indicator.linkedSkills as linkedSkill}
						<tr>
							<td>
								<a class="inline-link" href={skillHref(linkedSkill)}>
									{linkedSkill.publisher}/{linkedSkill.repo}/{linkedSkill.skillSlug}
								</a>
							</td>
							<td class="mono">{linkedSkill.versionLabel}</td>
							<td>{formatOptional(linkedSkill.extractionKind)}</td>
							<td class="mono">{formatOptional(linkedSkill.sourcePath)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="empty-state">No skills are currently linked to this indicator.</div>
	{/if}
</section>
