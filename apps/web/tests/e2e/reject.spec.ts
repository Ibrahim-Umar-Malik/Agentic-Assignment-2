import { expect, test } from "@playwright/test";
import { login, openFirstDraft } from "./helpers";

test("rejecting a draft requires a reason and records it", async ({ page }) => {
  await login(page);
  await openFirstDraft(page);
  await page.getByTestId("reject").click();
  await expect(page.getByTestId("confirm-reject")).toBeDisabled();
  await page.getByPlaceholder("e.g. rate too low").fill("rate too low for this client");
  await page.getByTestId("confirm-reject").click();
  await expect(page.getByTestId("decision-status")).toContainText("rejected", { timeout: 45_000 });
  await page.getByRole("link", { name: "Analytics" }).click();
  await expect(page.getByText("rate too low for this client")).toBeVisible();
});
