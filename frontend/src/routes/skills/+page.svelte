<script lang="ts">
	import {
		buildSkillHref,
		firstDomain,
		formatObservedAt,
		formatWeeklyInstalls,
		installTrendLabel,
		priorityTone,
		registryLabels,
		severityTone
	} from '$lib/presenters';
	import type { SkillSummary, SkillsPageFilters } from '$lib/types';

	let {
		data
	} = $props<{ data: { page: { items: SkillSummary[]; total: number; page: number; pageSize: number; hasNext: boolean; hasPrevious: boolean }; filters: SkillsPageFilters } }>();

	type InstallBucket = SkillsPageFilters['installBucket'];
	type SortMode = SkillsPageFilters['sort'];

	const severityOptions: Array<{ label: string; value: SkillsPageFilters['severity'] }> = [
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
		{ label: 'Weekly installs', value: 'installs' },
		{ label: 'Risk score', value: 'risk' },
		{ label: 'Growth', value: 'growth' }
	];

	const pageWeeklyInstalls = $derived.by(() =>
		data.page.items.reduce(
			(total: number, skill: SkillSummary) =>
				total + (skill.currentTotalInstalls ?? skill.currentWeeklyInstalls ?? 0),
			0
		)
	);
	const pagePriorityCount = $derived.by(
		() => data.page.items.filter((skill: SkillSummary) => skill.priorityScore >= 80).length
	);
	const pageTenKInstalls = $derived.by(
		() =>
			data.page.items.filter(
				(skill: SkillSummary) =>
					(skill.currentTotalInstalls ?? skill.currentWeeklyInstalls ?? 0) >= 10_000
			).length
	);
	const pageStart = $derived.by(() =>
		data.page.total === 0 ? 0 : (data.page.page - 1) * data.page.pageSize + 1
	);
	const pageEnd = $derived.by(() =>
		data.page.total === 0 ? 0 : pageStart + data.page.items.length - 1
	);
	const signalTooltip =
		'Signals are the SK Risk sub-scores: B = behavior score from the skill itself, I = external intelligence corroboration, and C = change score from version-to-version drift.';
	const priorityTooltip =
		'Priority combines the latest risk score, confidence, and install impact to rank which skills analysts should review first.';
	const topDomainTooltip =
		'Top domain shows the first extracted domain from the latest snapshot. It is a representative domain, not the most-contacted or most-frequent domain.';

	function buildPageHref(pageNumber: number): string {
		const params = new URLSearchParams();
		params.set('page', String(pageNumber));
		if (data.filters.query) {
			params.set('q', data.filters.query);
		}
		if (data.filters.severity !== 'all') {
			params.set('severity', data.filters.severity);
		}
		if (data.filters.installBucket !== 'all') {
			params.set('installs', data.filters.installBucket);
		}
		if (data.filters.sort !== 'priority') {
			params.set('sort', data.filters.sort);
		}
		return `/skills?${params.toString()}`;
	}
</script>

<section class="hero hero--compact">
	<div class="hero-grid">
		<div>
			<p class="section-eyebrow">Registry-wide analyst view</p>
			<h1>Skills registry</h1>
			<p>
				The queue now pages from the server instead of loading the entire registry into the
				browser. Filters are URL-driven so analysts can share exact slices of the corpus.
			</p>
		</div>

		<div class="hero-panel stack">
			<div class="kpi-line">
				<span class="muted">Matching skills</span>
				<strong>{data.page.total}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Showing</span>
				<strong>{pageStart}-{pageEnd}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Current page installs</span>
				<strong>{formatWeeklyInstalls(pageWeeklyInstalls)}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">Priority 80+ on page</span>
				<strong>{pagePriorityCount}</strong>
			</div>
			<div class="kpi-line">
				<span class="muted">10k+ installs on page</span>
				<strong>{pageTenKInstalls}</strong>
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

	<form class="toolbar" role="search" method="GET" action="/skills">
		<div class="field field--wide">
			<label for="skills-query">Search skills</label>
			<input
				id="skills-query"
				name="q"
				aria-label="Search skills"
				type="search"
				value={data.filters.query}
				placeholder="publisher / repo / skill title"
			/>
		</div>
		<div class="field">
			<label for="skills-severity">Severity</label>
			<select id="skills-severity" name="severity" aria-label="Severity">
				{#each severityOptions as option}
					<option value={option.value} selected={data.filters.severity === option.value}>
						{option.label}
					</option>
				{/each}
			</select>
		</div>
		<div class="field">
			<label for="skills-installs">Weekly installs</label>
			<select id="skills-installs" name="installs" aria-label="Weekly installs">
				{#each installBucketOptions as option}
					<option value={option.value} selected={data.filters.installBucket === option.value}>
						{option.label}
					</option>
				{/each}
			</select>
		</div>
		<div class="field">
			<label for="skills-sort">Sort by</label>
			<select id="skills-sort" name="sort" aria-label="Sort by">
				{#each sortOptions as option}
					<option value={option.value} selected={data.filters.sort === option.value}>
						{option.label}
					</option>
				{/each}
			</select>
		</div>
		<div class="toolbar-actions">
			<button class="action-button" type="submit">Apply filters</button>
		</div>
	</form>

	{#if data.page.items.length > 0}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th>Skill</th>
						<th>Registries</th>
						<th>
							<span class="table-help" title={priorityTooltip}>Priority</span>
						</th>
						<th>Total Installs</th>
						<th>Severity</th>
						<th>Confidence</th>
						<th>
							<span class="table-help" title={signalTooltip}>Signals</span>
						</th>
						<th>Indicators</th>
						<th>
							<span class="table-help" title={topDomainTooltip}>Top domain</span>
						</th>
					</tr>
				</thead>
				<tbody>
					{#each data.page.items as skill}
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
									<span class="table-subtext">Unknown</span>
								{/if}
							</td>
							<td>
								<span class="badge" data-level={priorityTone(skill.priorityScore)}>
									{skill.priorityScore}
								</span>
								<p class="table-subtext">impact {skill.impactScore}</p>
							</td>
							<td>
								<strong class="mono">
									{formatWeeklyInstalls(skill.currentTotalInstalls ?? skill.currentWeeklyInstalls)}
								</strong>
								<p class="table-subtext">
									{#if skill.installBreakdown.length > 0}
										{skill.installBreakdown
											.map(
												(entry: SkillSummary['installBreakdown'][number]) =>
													`${entry.sourceName} ${formatWeeklyInstalls(entry.weeklyInstalls)}`
											)
											.join(' · ')}
									{:else}
										{installTrendLabel(skill.weeklyInstallsDelta)}
									{/if}
									{' · '}
									{formatObservedAt(
										skill.currentTotalInstallsObservedAt ?? skill.currentWeeklyInstallsObservedAt
									)}
								</p>
							</td>
							<td>
								<span class="badge" data-level={severityTone(skill.latestSnapshot.riskReport.severity)}>
									{skill.latestSnapshot.riskReport.severity}
								</span>
							</td>
							<td>{skill.latestSnapshot.riskReport.confidence ?? 'unscored'}</td>
							<td class="mono">
								B {skill.latestSnapshot.riskReport.behaviorScore ?? 0} / I {skill.latestSnapshot.riskReport.intelScore ?? 0}
								/ C {skill.latestSnapshot.riskReport.changeScore ?? 0}
							</td>
							<td>{skill.latestSnapshot.riskReport.indicatorMatches.length}</td>
							<td class="mono">{firstDomain(skill.latestSnapshot.extractedDomains)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<div class="pagination-bar">
			<p class="muted">Page {data.page.page} · showing {pageStart}-{pageEnd} of {data.page.total}</p>
			<div class="pagination-actions">
				{#if data.page.hasPrevious}
					<a class="pagination-link" href={buildPageHref(data.page.page - 1)}>Previous page</a>
				{:else}
					<span class="pagination-link pagination-link--disabled">Previous page</span>
				{/if}

				{#if data.page.hasNext}
					<a class="pagination-link" href={buildPageHref(data.page.page + 1)}>Next page</a>
				{:else}
					<span class="pagination-link pagination-link--disabled">Next page</span>
				{/if}
			</div>
		</div>
	{:else}
		<div class="empty-state">No skills match the current filter set.</div>
	{/if}
</section>
