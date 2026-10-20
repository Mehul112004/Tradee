import { test, expect } from "@playwright/test";
const workspace = "?workspace=test";
test("real API overview reconciles funded paper wallet and labels synthetic data", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/" + workspace);
  await expect(page.getByText("328.49", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText("SYNTHETIC VERIFICATION", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("3 admitted · full rejection history retained"),
  ).toBeVisible();
  await expect(
    page.getByText("Service connected", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/overview-desktop.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
test("market chart uses actual candles and incomplete hourly buckets stay empty", async ({
  page,
}) => {
  await page.goto("/markets" + workspace);
  await expect(
    page.getByRole("img", { name: /actual closed OHLCV/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "1h", exact: true }).click();
  await expect(
    page.getByText("No complete candles in this range"),
  ).toBeVisible();
  await page.getByRole("button", { name: "1m", exact: true }).click();
  await expect(
    page.getByRole("img", { name: /actual closed OHLCV/ }),
  ).toBeVisible();
  await page.getByLabel("Two-chart workspace").check();
  await expect(
    page.getByRole("img", { name: /actual closed OHLCV/ }),
  ).toHaveCount(2);
  await page.getByLabel("Two-chart workspace").uncheck();
  await page.getByLabel("Instrument", { exact: true }).selectOption("ETHUSDT");
  await expect(
    page.getByRole("heading", { name: "ETHUSDT / USDT perpetual" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Coverage & gaps" }).click();
  await expect(
    page.getByText("Final minute keys", { exact: true }),
  ).toBeVisible();
});
test("signals retain rejections, details and decision snapshot; CSV is real", async ({
  page,
}) => {
  await page.goto("/signals" + workspace);
  await expect(page.locator("tbody tr")).toHaveCount(6);
  await page.getByRole("tab", { name: "Rejected", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await page.getByRole("button", { name: "BTCUSDT" }).first().click();
  await expect(page.getByLabel("Signal detail")).toBeVisible();
  await page
    .getByText("Decision-time C03 feature snapshot", { exact: true })
    .click();
  await expect(
    page
      .locator("details")
      .filter({
        has: page.locator("summary", {
          hasText: "Decision-time C03 feature snapshot",
        }),
      })
      .locator("pre"),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toBe("signals.csv");
});
test("knowledge cursor hides future cycles and operator controls are disabled", async ({
  page,
}) => {
  await page.goto("/signals" + workspace + "&at=1");
  await expect(
    page.getByText("No matching records", { exact: true }),
  ).toBeVisible();
  await page.goto("/operations" + workspace + "&at=1");
  await expect(
    page.getByRole("button", { name: /paper processing/ }),
  ).toBeDisabled();
});
test("portfolio funded outcomes and exact evidence are inspectable", async ({
  page,
}) => {
  await page.goto("/portfolio" + workspace);
  await expect(
    page.getByRole("heading", { name: "One wallet. Every constraint." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Drawdown from known peak" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Open positions" }).click();
  await expect(page.getByText("No open paper positions")).toBeVisible();
  await page.getByRole("tab", { name: "Funded trades" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await page
    .getByRole("button", { name: "BTCUSDT", exact: false })
    .first()
    .click();
  await expect(
    page.getByText("Funded trade evidence", { exact: true }),
  ).toBeVisible();
});
test("research inspects frozen folds, simulation coverage and model bounds", async ({
  page,
}) => {
  await page.goto("/research" + workspace);
  await page.getByRole("button", { name: "funded_engineering" }).click();
  await expect(
    page.getByRole("heading", { name: "Chronological ownership" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Simulation runs", exact: true }).click();
  await page.locator(".row-open").first().click();
  await expect(
    page.getByRole("heading", { name: "Run inspection", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Models", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Expectancy models" }),
  ).toBeVisible();
});
test("forward immutable report selection preserves insufficient statistical reviews", async ({
  page,
}) => {
  await page.goto("/forward" + workspace);
  await expect(
    page.getByText("Insufficient", { exact: true }).first(),
  ).toBeVisible();
  const select = page.getByLabel("Report vintage", { exact: true });
  const first = await select.locator("option").nth(1).getAttribute("value");
  await select.selectOption(first!);
  await expect(
    page.getByText("Fixed review schedule", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Actual user fills", { exact: true }),
  ).toHaveCount(0);
});
test("data quality links selected dataset to registry rules", async ({
  page,
}) => {
  await page.goto("/data" + workspace);
  await page.locator(".row-open").first().click();
  await expect(
    page.getByRole("heading", { name: "Dataset quality", exact: true }),
  ).toBeVisible();
  await page.getByText("Quality report", { exact: true }).click();
  await expect(
    page
      .locator("details")
      .filter({ has: page.locator("summary", { hasText: /^Quality report$/ }) })
      .locator("pre"),
  ).toContainText("gap");
});
test("viewer cannot control; memory-only token queues and worker executes revision-checked resume", async ({
  page,
}) => {
  await page.goto("/operations" + workspace);
  await expect(
    page.getByRole("button", { name: "Resume paper processing" }),
  ).toBeDisabled();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page
    .getByLabel("Operator token", { exact: true })
    .fill("e2e-test-only");
  await page.getByRole("button", { name: "Enable operator requests" }).click();
  await page.getByRole("link", { name: "Operations", exact: true }).click();
  await page
    .getByPlaceholder("Explain the operational reason…")
    .fill("Browser E2E verified paper state");
  await page
    .getByLabel(
      "I reviewed the session, current source age and intended state.",
    )
    .check();
  await page.getByRole("button", { name: "Resume paper processing" }).click();
  await expect(page.getByRole("status")).toContainText("queued");
  await page.getByRole("tab", { name: "Job history", exact: true }).click();
  await page.getByRole("button", { name: "Refresh all evidence" }).click();
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible({
    timeout: 15000,
  });
  expect(
    await page.evaluate(() => localStorage.length + sessionStorage.length),
  ).toBe(0);
  await page.reload();
  await page.getByRole("tab", { name: "Sessions & controls" }).click();
  await expect(
    page.getByRole("button", { name: "Pause paper processing" }),
  ).toBeDisabled();
});
test("all routes work at mobile size without page overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of [
    "/",
    "/markets",
    "/signals",
    "/portfolio",
    "/research",
    "/forward",
    "/data",
    "/operations",
    "/settings",
  ]) {
    await page.goto(path + workspace);
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.getByText("This view could not render")).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
  }
  await page.goto("/" + workspace);
  await page.screenshot({
    path: "test-results/overview-mobile.png",
    fullPage: true,
  });
});
