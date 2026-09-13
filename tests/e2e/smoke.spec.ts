import { expect, test } from "@playwright/test";

const PAGES: { nav: string; heading: string }[] = [
  { nav: "Overview", heading: "Overview" },
  { nav: "Analytics", heading: "Analytics" },
  { nav: "Funnels", heading: "Funnels" },
  { nav: "Cohorts", heading: "Cohorts" },
  { nav: "Segments", heading: "Segments" },
  { nav: "Experiments", heading: "Experiments" },
  { nav: "Investigations", heading: "Investigations" },
  { nav: "Analyst", heading: "Analyst" },
  { nav: "Product Ops", heading: "Product Ops" },
  { nav: "Releases", heading: "Releases" },
  { nav: "Decisions", heading: "Decision log" },
  { nav: "Settings", heading: "Settings" },
];

test("login lands on overview", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
});

test("every page loads and the worker is alive", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  for (const { nav, heading } of PAGES) {
    await page.getByRole("link", { name: nav, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }

  await page.getByRole("tab", { name: "System" }).click();
  await expect(page.getByText("Alive", { exact: false })).toBeVisible();

  await page.getByRole("link", { name: "Experiments", exact: true }).click();
  await page.locator("table a").first().click();
  await expect(page).toHaveURL(/\/experiments\/\d+/);
  await expect(page.getByRole("heading", { name: "Design" })).toBeVisible();

  await page.getByRole("link", { name: "Investigations", exact: true }).click();
  await page.locator("table a").first().click();
  await expect(page).toHaveURL(/\/investigations\/\d+/);
});
