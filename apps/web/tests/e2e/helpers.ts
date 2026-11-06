import { expect, type Page } from "@playwright/test";

export const REVIEWER = { email: "e2e-reviewer@example.test", password: "e2e-only-password" };

export async function login(page: Page, base = "", who = REVIEWER) {
  await page.goto(`${base}/login`);
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.locator("form button[type=submit]").click();
  await page.waitForURL(/\/(inbox|onboarding)/);
  if (page.url().includes("onboarding")) {
    await page.getByTestId("finish-onboarding").click();
    await page.waitForURL(/\/inbox/);
  }
}

/** Scout, wait for the graph to draft a proposal, and open the first one in the studio. */
export async function openFirstDraft(page: Page) {
  await page.getByTestId("scout-now").click();
  const review = page.getByRole("link", { name: "Review draft" });
  await expect(async () => {
    await page.reload();
    await expect(review.first()).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 60_000, intervals: [1000, 2000] });
  // each test takes a draft nobody has decided yet
  await review.first().click();
  await expect(page.getByTestId("approval-panel")).toBeVisible();
}
