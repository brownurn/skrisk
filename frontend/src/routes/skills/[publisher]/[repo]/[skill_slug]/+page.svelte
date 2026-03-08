<script lang="ts">
	import {
		buildIndicatorHref,
		formatInstallDelta,
		formatInstallHistoryContext,
		formatObservationKind,
		formatObservedAt,
		formatOptional,
		formatWeeklyInstalls,
		installTrendLabel,
		installTrendTone,
		priorityCardTone,
		priorityTone,
		severityTone
	} from '$lib/presenters';
	import type { SkillDetail, SkillIndicatorLink } from '$lib/types';

	let { data } = $props<{ data: { skill: SkillDetail } }>();

	const snapshot = $derived(data.skill.latestSnapshot);
	const indicatorLinks = $derived(snapshot.indicatorLinks ?? []);
	const installHistory = $derived(data.skill.installHistory ?? []);

	function linkHref(link: SkillIndicatorLink): string {
		return buildIndicatorHref(link.indicatorType ?? 'domain', link.indicatorValue ?? '');
	}
</script>

<section class="hero hero--compact">
	<div class="hero-grid">
		<div>
			<p class="section-eyebrow">Skill evidence dossier</p>
			<h1>{data.skill.title}</h1>
			<p class="hero-coordinate mono">
				{data.skill.publisher}/{data.skill.repo}/{data.skill.skillSlug}
			</p>
			<p>
				Review the latest snapshot, extracted infrastructure, and evidence trail behind the
				current risk posture.
			</p>
			<div class="summary-strip">
				<span class="badge" data-level={severityTone(snapshot.riskReport.severity)}>
					{snapshot.riskReport.severity}
				</span>
				<span class="badge" data-level={priorityTone(data.skill.priorityScore)}>
					priority {data.skill.priorityScore}
				</span>
				<span class="token">impact {data.skill.impactScore}</span>
				<span class="token">weekly installs {formatWeeklyInstalls(data.skill.currentWeeklyInstalls)}</span>
				<span class="token">version {snapshot.versionLabel || 'unknown'}</span>
				<span class="token">confidence {snapshot.riskReport.confidence ?? 'unscored'}</span>
			</div>
		</div>

		<div class="hero-panel stack">
			<div class="kpi-line">
				<span class="muted">Registry path</span>
				<strong class="mono">{data.skill.relativePath}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Latest installs</span>
				<strong>{formatWeeklyInstalls(data.skill.currentWeeklyInstalls)}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Peak installs</span>
				<strong>{formatWeeklyInstalls(data.skill.peakWeeklyInstalls)}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Last observed</span>
				<strong>{formatObservedAt(data.skill.currentWeeklyInstallsObservedAt)}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Risk score</span>
				<strong>{snapshot.riskReport.score}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Indicators</span>
				<strong>{indicatorLinks.length}</strong>
			</div>
		</div>
	</div>
</section>

<section class="metric-grid">
	<article class="metric-card">
		<p class="metric-label">Latest Weekly Installs</p>
		<p class="metric-value">{formatWeeklyInstalls(data.skill.currentWeeklyInstalls)}</p>
		<p class="muted">{formatObservedAt(data.skill.currentWeeklyInstallsObservedAt)}</p>
	</article>
	<article class="metric-card">
		<p class="metric-label">Peak Weekly Installs</p>
		<p class="metric-value">{formatWeeklyInstalls(data.skill.peakWeeklyInstalls)}</p>
		<p class="muted">Highest observed footprint</p>
	</article>
	<article class="metric-card" data-tone={installTrendTone(data.skill.weeklyInstallsDelta)}>
		<p class="metric-label">Install Delta</p>
		<p class="metric-value">{formatInstallDelta(data.skill.weeklyInstallsDelta)}</p>
		<p class="muted">{installTrendLabel(data.skill.weeklyInstallsDelta)} week over week</p>
	</article>
	<article class="metric-card" data-tone={priorityCardTone(data.skill.priorityScore)}>
		<p class="metric-label">Priority</p>
		<p class="metric-value">{data.skill.priorityScore}</p>
		<p class="muted">Risk and reach combined</p>
	</article>
	<article class="metric-card" data-tone="accent">
		<p class="metric-label">Impact</p>
		<p class="metric-value">{data.skill.impactScore}</p>
		<p class="muted">Install footprint only</p>
	</article>
	<article class="metric-card">
		<p class="metric-label">Behavior Score</p>
		<p class="metric-value">{snapshot.riskReport.behaviorScore ?? 0}</p>
	</article>
	<article class="metric-card" data-tone="critical">
		<p class="metric-label">Intel Score</p>
		<p class="metric-value">{snapshot.riskReport.intelScore ?? 0}</p>
	</article>
	<article class="metric-card" data-tone="accent">
		<p class="metric-label">Change Score</p>
		<p class="metric-value">{snapshot.riskReport.changeScore ?? 0}</p>
	</article>
	<article class="metric-card" data-tone="success">
		<p class="metric-label">Findings</p>
		<p class="metric-value">{snapshot.riskReport.findings.length}</p>
	</article>
</section>

<section class="panel-grid">
	<div class="table-card">
		<div class="table-header">
			<div>
				<p class="table-label">Behavioral evidence</p>
				<h2>Behavior findings</h2>
			</div>
			{#if data.skill.registryUrl}
				<a class="inline-link" href={data.skill.registryUrl} target="_blank" rel="noreferrer">
					Open registry entry
				</a>
			{/if}
		</div>

		{#if snapshot.riskReport.findings.length > 0}
			<div class="table-wrap">
				<table>
					<thead>
						<tr>
							<th>Path</th>
							<th>Category</th>
							<th>Severity</th>
							<th>Evidence</th>
						</tr>
					</thead>
					<tbody>
						{#each snapshot.riskReport.findings as finding}
							<tr>
								<td class="mono">{finding.path}</td>
								<td>{finding.category}</td>
								<td>
									<span class="badge" data-level={severityTone(finding.severity)}>
										{finding.severity}
									</span>
								</td>
								<td>{finding.evidence}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{:else}
			<div class="empty-state">No explicit findings were recorded on the latest snapshot.</div>
		{/if}
	</div>

	<div class="panel stack">
		<div>
			<p class="table-label">Snapshot context</p>
			<h2>Risk profile</h2>
		</div>

		<div class="definition-grid">
			<div class="definition-card">
				<h3>Categories</h3>
				<div class="token-list">
					{#if snapshot.riskReport.categories.length > 0}
						{#each snapshot.riskReport.categories as category}
							<span class="token">{category}</span>
						{/each}
					{:else}
						<span class="muted">No categories recorded</span>
					{/if}
				</div>
			</div>

			<div class="definition-card">
				<h3>Referenced files</h3>
				<div class="token-list">
					{#if snapshot.referencedFiles.length > 0}
						{#each snapshot.referencedFiles as file}
							<span class="token mono">{file}</span>
						{/each}
					{:else}
						<span class="muted">No referenced files extracted</span>
					{/if}
				</div>
			</div>
		</div>

		<div class="definition-card">
			<h3>Extracted domains</h3>
			<div class="token-list">
				{#if snapshot.extractedDomains.length > 0}
					{#each snapshot.extractedDomains as domain}
						<span class="token mono">{domain}</span>
					{/each}
				{:else}
					<span class="muted">No domains extracted</span>
				{/if}
			</div>
		</div>

		<div class="definition-card">
			<h3>Partner verdicts</h3>
			<div class="stack stack-tight">
				{#if data.skill.externalVerdicts.length > 0}
					{#each data.skill.externalVerdicts as verdict}
						<div>
							<p><strong>{verdict.partner}</strong> · {verdict.verdict}</p>
							<p class="muted">{formatOptional(verdict.summary)}</p>
						</div>
					{/each}
				{:else}
					<p class="muted">No partner verdicts recorded for this skill yet.</p>
				{/if}
			</div>
		</div>
	</div>
</section>

<section class="table-card page-section">
	<div class="table-header">
		<div>
			<p class="table-label">Install telemetry</p>
			<h2>Install history</h2>
		</div>
	</div>

	{#if installHistory.length > 0}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th>Observed</th>
						<th>Weekly installs</th>
						<th>Observation</th>
						<th>Context</th>
					</tr>
				</thead>
				<tbody>
					{#each installHistory as entry}
						<tr>
							<td class="mono">{formatObservedAt(entry.observedAt)}</td>
							<td class="mono">{formatWeeklyInstalls(entry.weeklyInstalls)}</td>
							<td>{formatObservationKind(entry.observationKind)}</td>
							<td>{formatInstallHistoryContext(entry)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="empty-state">
			Install telemetry will appear after the next registry sync or scan attribution.
		</div>
	{/if}
</section>

<section class="table-card page-section">
	<div class="table-header">
		<div>
			<p class="table-label">Infrastructure links</p>
			<h2>Indicator links</h2>
		</div>
	</div>

	{#if indicatorLinks.length > 0}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th>Indicator</th>
						<th>Extraction</th>
						<th>Source path</th>
						<th>Snapshot delta</th>
					</tr>
				</thead>
				<tbody>
					{#each indicatorLinks as link}
						<tr>
							<td>
								<a class="inline-link mono" href={linkHref(link)}>
									{link.indicatorValue}
								</a>
								<p class="table-subtext">{link.indicatorType}</p>
							</td>
							<td>{formatOptional(link.extractionKind)}</td>
							<td class="mono">{formatOptional(link.sourcePath)}</td>
							<td>{link.isNewInSnapshot ? 'New in latest snapshot' : 'Seen previously'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="empty-state">No linked indicators were recorded on this snapshot.</div>
	{/if}
</section>
