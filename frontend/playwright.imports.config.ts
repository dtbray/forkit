import { defineConfig } from '@playwright/test';

export default defineConfig({
	testMatch: ['tests/wordpress-import.e2e.ts', 'tests/recipe-controls.e2e.ts'],
	webServer: { command: 'npm run preview -- --host 127.0.0.1', port: 4173 },
	use: { baseURL: 'http://127.0.0.1:4173', serviceWorkers: 'block' },
	projects: [
		{ name: 'desktop', use: { browserName: 'chromium', viewport: { width: 1440, height: 900 } } },
		{ name: 'phone', use: { browserName: 'chromium', viewport: { width: 390, height: 844 } } }
	]
});
