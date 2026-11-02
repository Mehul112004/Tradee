import { test, expect } from "@playwright/test";

async function authorize(page: import("@playwright/test").Page) {
  await page.goto("/analysis?workspace=local");
  await expect(page.locator(".analysis-access")).toBeVisible();
  if ((await page.locator(".analysis-access").getAttribute("open")) === null) {
    await page
      .locator("summary")
      .filter({ hasText: "Enable session controls" })
      .click();
  }
  await page
    .getByLabel("Operator token", { exact: true })
    .fill("e2e-test-only");
  await page
    .getByRole("button", { name: "Enable session controls", exact: true })
    .click();
}

test("history scan prepares data, shows strategy levels and saves setup explanations", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await authorize(page);
  await page.getByRole("button", { name: "New analysis session" }).click();
  await page.getByLabel("Session name").fill("Historical walkthrough");
  await page
    .getByLabel("Instruments", { exact: true })
    .fill("BTCUSDT, ETHUSDT");
  await page.getByLabel("What would you like to do?").selectOption("history");
  await page.getByLabel("Historical candles to scan").selectOption("100");
  await page.getByLabel("EMA pullback", { exact: false }).check();
  await page.getByRole("button", { name: "Scan historical setups" }).click();
  await expect(
    page.getByRole("heading", { name: "Chart and reference levels" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByText("Historical scan · alerts off", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /BTCUSDT actual closed OHLCV/ }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator(".candle-host")
        .evaluate(
          (host) =>
            Math.max(
              ...Array.from(host.querySelectorAll("canvas")).map(
                (c) => c.getBoundingClientRect().width,
              ),
            ) / host.getBoundingClientRect().width,
        ),
    )
    .toBeGreaterThan(0.7);
  await expect(
    page.getByText("Previous 20 candles · high", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "BTCUSDT", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "Return to latest chart" }),
  ).toBeVisible();
  await expect(
    page.getByText("Reference close:", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Return to latest chart" }).click();
  await page.getByLabel("Chart instrument").selectOption("ETHUSDT");
  await expect(
    page.getByRole("img", { name: /ETHUSDT actual closed OHLCV/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/analysis-history-desktop.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("live session pauses, resumes, stops, and reload clears control authorization", async ({
  page,
}) => {
  await authorize(page);
  await page.getByRole("button", { name: "New analysis session" }).click();
  await page.getByLabel("Session name").fill("Live walkthrough");
  await page.getByRole("button", { name: "Start watching" }).click();
  await expect(
    page.getByText("Watching for setups", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByText("Binance WebSocket: connected", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: "BTCUSDT live OHLCV candles" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Forming candles update the chart only. Setups require a complete candle close.",
      { exact: false },
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Resume", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Resume", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Pause", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect(page.getByText("Stopped", { exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "New analysis session" }).click();
  await expect(
    page.getByRole("button", { name: "Start watching" }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Operator token", { exact: true }),
  ).toBeVisible();
});

test("synthetic evidence stays separate and analysis fits mobile", async ({
  page,
}) => {
  await page.goto("/analysis?workspace=test");
  await expect(
    page.getByText("This workspace contains retained synthetic research.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start watching" }),
  ).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/analysis?workspace=local");
  await page.getByRole("button", { name: "New analysis session" }).click();
  await expect(
    page.getByRole("heading", { name: "Analysis sessions", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/analysis-mobile.png",
    fullPage: true,
  });
});

test("structural pilots prepare hourly context automatically and retain pattern-only history", async ({
  page,
}) => {
  await authorize(page);
  await page.getByRole("button", { name: "New analysis session" }).click();
  await page.getByLabel("Session name").fill("Structural pilot walkthrough");
  await page.getByLabel("What would you like to do?").selectOption("history");
  await page.getByLabel("Historical candles to scan").selectOption("100");
  await page.getByLabel("Strategy timeframe").selectOption("1m");
  await page.getByLabel("Liquidity sweep", { exact: false }).check();
  await page.getByLabel("200 EMA rejection", { exact: false }).check();
  await page.getByLabel("Key-level retest", { exact: false }).check();
  await expect(page.getByLabel("Strategy timeframe")).toHaveValue("15m");
  await expect(page.getByLabel("Strategy timeframe")).toBeDisabled();
  await page.getByLabel("Range breakout", { exact: false }).uncheck();
  await page.getByRole("button", { name: "Scan historical setups" }).click();
  await expect(page.getByText(/complete hourly candles prepared/)).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByText(/Historical scans measure patterns only/),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /BTCUSDT actual closed OHLCV/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/structural-pilots-history.png",
    fullPage: true,
  });
});
