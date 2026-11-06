import { expect, test } from "@playwright/test";

test("a new freelancer signs up, picks a persona and lands on the inbox", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /create an account/i }).click();
  const email = `new-${Date.now()}@example.test`;
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("a-long-password-1");
  await page.getByLabel("Name").fill("New Freelancer");
  await page.locator("form button[type=submit]").click();
  await page.waitForURL(/\/onboarding/);
  await page.getByLabel("Hourly floor (USD)").fill("50");
  await page.getByTestId("finish-onboarding").click();
  await page.waitForURL(/\/inbox/);
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByLabel("Hourly floor (USD)")).toHaveValue("50");
});
