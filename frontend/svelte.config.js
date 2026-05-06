import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// SPA mode — pre-rendered shell, client-side routing.
		// ADR-001 §3a: no SSR runtime in container; SPA + service worker is the PWA story.
		adapter: adapter({ fallback: 'index.html' })
	}
};

export default config;
