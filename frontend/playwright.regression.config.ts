import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
	baseURL: 'http://localhost:8080/',
	webServer: undefined,
	testMatch: 'tests/cook-flow-regression.spec.ts',
	projects: [
		{
			name: 'chromium',
			use: { ...devices['Desktop Chrome'] }
		}
	],
	use: {
		screenshot: 'only-on-failure',
		trace: 'on-first-retry'
	},
	timeout: 60000,
	expect: { timeout: 10000 }
});
