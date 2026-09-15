import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8010',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'cd .. && npm --prefix frontend run build && uv run uvicorn src.main:app --host 127.0.0.1 --port 8010',
    url: 'http://127.0.0.1:8010/api/health',
    reuseExistingServer: false,
    env: {
      ...process.env,
      DATABASE_PATH: '/tmp/agent-eval-harness-playwright.db',
      STATIC_DIR: 'frontend/dist',
      ...(process.env.RUN_LIVE_UI === '1' ? {} : {
        OPENAI_API_KEY: '', GEMINI_API_KEY: '', OPENROUTER_API_KEY: '', OPENCODE_API_KEY: '',
      }),
    },
  },
})
