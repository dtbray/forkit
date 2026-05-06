import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
	webServer: { command: 'npm run build && npm run preview', port: 4173 },
	testMatch: '**/*.e2e.{ts,js}',
	projects: [
		// Primary lane — ADR-001 §3a: iPad Pro 12.9" landscape is canonical reference UI
		{
			name: 'ipad-landscape',
			use: { ...devices['iPad Pro 12.9 landscape'] }
		},
		// Secondary — iPhone portrait
		{
			name: 'iphone-portrait',
			use: { ...devices['iPhone 14 Pro'] }
		},
		// Desktop
		{
			name: 'desktop',
			use: { viewport: { width: 1440, height: 900 } }
		}
	]
});
