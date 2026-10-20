import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:8790",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
  ],
  webServer: {
    command: `${process.env.TRADEE_PYTHON || "python"} -m scripts.serve_dashboard_e2e`,
    cwd: "..",
    url: "http://127.0.0.1:8790/api/health",
    timeout: 180000,
    reuseExistingServer: false,
    stdout: "pipe",
    stderr: "pipe",
  },
});
