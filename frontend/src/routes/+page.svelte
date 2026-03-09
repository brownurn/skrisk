<script lang="ts">
	import { firstDomain, formatWeeklyInstalls, severityTone } from '$lib/presenters';
	import type { OverviewData } from '$lib/types';

	let { data } = $props<{ data: OverviewData }>();

	function totalInstalls(value: number | null, fallback: number | null): number | null {
		return value ?? fallback;
	}
</script>

<section class="hero">
	<div class="hero-grid">
		<div>
			<p class="section-eyebrow">Evidence-first analyst console</p>
			<h1>Track AI skill behavior, infrastructure, and change risk.</h1>
			<p>
				SK Risk correlates static skill analysis with Abuse.ch and VirusTotal context, then
				surfaces the evidence trail instead of hiding it behind a black-box score.
			</p>
			<div class="code-note">
				<code>72h scan cadence · selective VT triage · immutable feed archives</code>
			</div>
		</div>

		<div class="hero-panel stack">
			<div>
				<p class="metric-label">Current branch posture</p>
				<p class="metric-value">{data.stats.criticalSkills} critical skills</p>
			</div>
			<div class="kpi-line">
				<span class="muted">Intel-backed findings</span>
				<strong>{data.stats.intelBackedFindings}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Pending VT queue</span>
				<strong>{data.stats.pendingVtQueue}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Recent feed runs</span>
				<strong>{data.feedRuns.length}</strong>
			</div>
		</div>
	</div>
</section>

<section class="metric-grid" aria-label="Overview metrics">
	<article class="metric-card" data-tone="accent">
		<p class="metric-label">Tracked Repos</p>
		<p class="metric-value">{data.stats.trackedRepos}</p>
	</article>
	<article class="metric-card">
		<p class="metric-label">Tracked Skills</p>
		<p class="metric-value">{data.stats.trackedSkills}</p>
	</article>
	<article class="metric-card" data-tone="critical">
		<p class="metric-label">Intel-Backed Findings</p>
		<p class="metric-value">{data.stats.intelBackedFindings}</p>
	</article>
	<article class="metric-card" data-tone="success">
		<p class="metric-label">Pending VT Queue</p>
		<p class="metric-value">{data.stats.pendingVtQueue}</p>
	</article>
</section>

<section class="panel-grid panel-grid--overview">
	<div class="table-card">
		<div class="table-header">
			<div>
				<p class="table-label">High urgency</p>
				<h2>Critical Skills</h2>
			</div>
			<a class="inline-link" href="/skills">View all skills</a>
		</div>

		{#if data.criticalSkills.length > 0}
			<div class="table-wrap">
				<table>
					<thead>
						<tr>
							<th>Skill</th>
							<th>Registries</th>
							<th>Total Installs</th>
							<th>Severity</th>
							<th>Top Domain</th>
						</tr>
					</thead>
					<tbody>
						{#each data.criticalSkills as skill}
							<tr>
								<td>
									<a
										class="inline-link"
										href={`/skills/${skill.publisher}/${skill.repo}/${skill.skillSlug}`}
									>
										{skill.publisher}/{skill.repo}/{skill.skillSlug}
									</a>
								</td>
								<td>
									<div class="token-list">
										{#each skill.sources as source}
											<span class="token">{source}</span>
										{/each}
									</div>
								</td>
								<td class="mono">
									{formatWeeklyInstalls(totalInstalls(skill.currentTotalInstalls, skill.currentWeeklyInstalls))}
								</td>
								<td>
									<span
										class="badge"
										data-level={severityTone(skill.latestSnapshot.riskReport.severity)}
									>
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
			<div class="empty-state">Run a registry sync to populate the first analyst queue.</div>
		{/if}
	</div>

	<div class="panel stack">
		<div class="panel-header">
			<div>
				<p class="table-label">Recent intelligence</p>
				<h2>Feed activity and VT budget</h2>
			</div>
			<a class="inline-link" href="/queue/vt">Inspect queue</a>
		</div>

		<div class="definition-grid">
			<div class="definition-card">
				<h3>Budget Remaining</h3>
				<p class="metric-value">{data.vtQueue.dailyBudgetRemaining}</p>
			</div>
			<div class="definition-card">
				<h3>Budget Used</h3>
				<p class="metric-value">{data.vtQueue.dailyBudgetUsed}</p>
			</div>
		</div>

		<div class="stack">
			{#each data.feedRuns as feedRun}
				<div class="definition-card">
					<h3>{feedRun.provider} / {feedRun.feedName}</h3>
					<p class="mono">{feedRun.sourceUrl}</p>
					<p class="muted">{feedRun.artifacts?.length ?? 0} archived artifacts</p>
				</div>
			{/each}
		</div>
	</div>
</section>
