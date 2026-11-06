import { expect, test } from "@playwright/test";
import { login } from "./helpers";

const DOWN = "http://127.0.0.1:8192";

test("when the marketplace is unreachable the UI says so instead of failing", async ({ page }) => {
  await login(page, DOWN);
  await page.getByTestId("scout-now").click();
  await expect(page.getByRole("status")).toContainText(/unavailable/i);
  await page.reload();
  await expect(page.getByTestId("degraded-banner")).toBeVisible();
  await expect(page.getByTestId("degraded-banner")).toContainText(/nothing is lost/i);
});
