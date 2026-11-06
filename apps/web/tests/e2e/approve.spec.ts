import { expect, test } from "@playwright/test";
import { login, openFirstDraft } from "./helpers";

test("approving a draft submits it and spends Connects", async ({ page }) => {
  await login(page);
  await openFirstDraft(page);
  const cost = await page.getByTestId("connects-cost").textContent();
  expect(Number(cost)).toBeGreaterThan(0);
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("decision-status")).toContainText("submitted", { timeout: 45_000 });
  await page.getByRole("link", { name: "Pipeline" }).click();
  await expect(page.getByRole("region", { name: "submitted" }).locator(".kcard")).not.toHaveCount(0);
});
