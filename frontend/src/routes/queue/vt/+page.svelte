<script lang="ts">
	import { buildIndicatorHref } from '$lib/presenters';
	import type { VTQueueStatus } from '$lib/types';

	let { data } = $props<{ data: { queue: VTQueueStatus } }>();

	const usagePercent = $derived(
		Math.min(
			100,
			Math.round((data.queue.dailyBudgetUsed / Math.max(1, data.queue.dailyBudget)) * 100)
		)
	);
</script>

<section class="hero hero--compact">
	<div class="hero-grid">
		<div>
			<p class="section-eyebrow">Selective enrichment control</p>
			<h1>VirusTotal queue</h1>
			<p>
				VT lookups are scarce. This queue exists to confirm the highest-risk skill indicators
				without burning the daily budget on low-signal infrastructure.
			</p>
			<div class="progress-card">
				<div class="progress-row">
					<span class="muted">Daily budget usage</span>
					<strong>{usagePercent}%</strong>
				</div>
				<div class="progress-bar" aria-hidden="true">
					<div class="progress-fill" style={`width: ${usagePercent}%`}></div>
				</div>
			</div>
		</div>

		<div class="hero-panel stack">
			<div class="kpi-line">
				<span class="muted">Daily budget</span>
				<strong>{data.queue.dailyBudget}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Used today</span>
				<strong>{data.queue.dailyBudgetUsed}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Remaining</span>
				<strong>{data.queue.dailyBudgetRemaining}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Pending items</span>
				<strong>{data.queue.queueItems.length}</strong>
			</div>
		</div>
	</div>
</section>

<section class="metric-grid">
	<article class="metric-card" data-tone="accent">
		<p class="metric-label">Daily VT Budget</p>
		<p class="metric-value">{data.queue.dailyBudget}</p>
	</article>
	<article class="metric-card">
		<p class="metric-label">Used Today</p>
		<p class="metric-value">{data.queue.dailyBudgetUsed}</p>
	</article>
	<article class="metric-card" data-tone="success">
		<p class="metric-label">Remaining</p>
		<p class="metric-value">{data.queue.dailyBudgetRemaining}</p>
	</article>
	<article class="metric-card" data-tone="critical">
		<p class="metric-label">Queued IOCs</p>
		<p class="metric-value">{data.queue.queueItems.length}</p>
	</article>
</section>

<section class="table-card page-section">
	<div class="table-header">
		<div>
			<p class="table-label">Escalation candidates</p>
			<h2>Queued indicators</h2>
		</div>
	</div>

	{#if data.queue.queueItems.length > 0}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th>Indicator</th>
						<th>Priority</th>
						<th>Status</th>
						<th>Attempts</th>
						<th>Reason</th>
					</tr>
				</thead>
				<tbody>
					{#each data.queue.queueItems as item}
						<tr>
							<td>
								<a
									class="inline-link mono"
									href={buildIndicatorHref(item.indicatorType, item.indicatorValue)}
								>
									{item.indicatorValue}
								</a>
								<p class="table-subtext">{item.indicatorType}</p>
							</td>
							<td>{item.priority}</td>
							<td>{item.status}</td>
							<td>{item.attemptCount}</td>
							<td>{item.reason}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="empty-state">No indicators are waiting for VirusTotal triage.</div>
	{/if}
</section>
