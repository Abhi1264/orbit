import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/login");
  await expect(page.getByLabel("Email")).toHaveValue("priya.pm@threadline.test");
  const login = page.waitForResponse(
    (r) => r.url().includes("/api/auth/login") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign in" }).click();
  expect((await login).ok(), "login should succeed").toBeTruthy();
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible({
    timeout: 15_000,
  });
}

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
  await signIn(page);
});

test("every page loads and the worker is alive", async ({ page }) => {
  test.setTimeout(90_000);
  await signIn(page);

  for (const { nav, heading } of PAGES) {
    await page.getByRole("link", { name: nav, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
  }

  await page.getByRole("tab", { name: "System" }).click();
  await expect(page.getByText("Alive", { exact: false })).toBeVisible({ timeout: 15_000 });

  await page.getByRole("link", { name: "Experiments", exact: true }).click();
  await page.locator("table a").first().click();
  await expect(page).toHaveURL(/\/experiments\/\d+/);
  await expect(page.getByRole("heading", { name: "Design" })).toBeVisible();

  await page.getByRole("link", { name: "Investigations", exact: true }).click();
  await page.locator("table a").first().click();
  await expect(page).toHaveURL(/\/investigations\/\d+/);
});
