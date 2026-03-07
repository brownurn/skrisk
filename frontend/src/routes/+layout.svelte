<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();

	const primaryNav = [
		{ href: '/', label: 'Overview' },
		{ href: '/skills', label: 'Skills' },
		{ href: '/queue/vt', label: 'VT Queue' }
	];
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<meta name="theme-color" content="#0f172a" />
	<title>SK Risk</title>
</svelte:head>

<div class="shell">
	<header class="topbar">
		<div class="brand-lockup">
			<a class="brand-mark" href="/" aria-label="SK Risk home">SK</a>
			<div>
				<p class="eyebrow">Melurna Intelligence</p>
				<a class="brand-title" href="/">SK Risk</a>
			</div>
		</div>

		<nav class="topnav" aria-label="Primary">
			{#each primaryNav as item}
				<a class="topnav-link" href={item.href}>{item.label}</a>
			{/each}
		</nav>
	</header>

	<main class="shell-main">
		{@render children()}
	</main>
</div>
