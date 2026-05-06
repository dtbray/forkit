import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
	plugins: [
		sveltekit(),
		VitePWA({
			registerType: 'autoUpdate',
			devOptions: { enabled: true },
			manifest: {
				name: 'forkit',
				short_name: 'forkit',
				description: 'Your family recipe vault',
				theme_color: '#F8F4EC',
				background_color: '#F8F4EC',
				display: 'standalone',
				start_url: '/',
				scope: '/',
				icons: [
					{ src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
					{
						src: '/icons/icon-512.png',
						sizes: '512x512',
						type: 'image/png',
						purpose: 'any maskable'
					}
				],
				// Share Target API — ADR-001 §3g
				// Requires PWA to be installed (iOS 16.4+)
				share_target: {
					action: '/ingest/share',
					method: 'GET',
					params: { url: 'url', title: 'title', text: 'text' }
				}
			},
			workbox: {
				globPatterns: ['**/*.{js,css,html,ico,png,svg,webp}'],
				runtimeCaching: [
					{
						// Cache recipe detail API responses — ADR-001 §3g: cache-first for favorites/last-20-viewed
						urlPattern: /^\/api\/recipes\/[^/]+$/,
						handler: 'CacheFirst',
						options: {
							cacheName: 'recipes-cache',
							expiration: { maxAgeSeconds: 60 * 60 * 24 * 7 }
						}
					},
					{
						// Cache image variants — ADR-001 §3g: cache-first for recipe images
						urlPattern: /^\/data\/images\//,
						handler: 'CacheFirst',
						options: {
							cacheName: 'images-cache',
							expiration: { maxAgeSeconds: 60 * 60 * 24 * 30 }
						}
					}
				]
			}
		})
	],
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
