import { expect, test } from "@playwright/test";
import { login, openFirstDraft } from "./helpers";

test("an edited draft is re-checked before it can be sent", async ({ page }) => {
  await login(page);
  await openFirstDraft(page);
  await page.getByTestId("edit").click();
  const editor = page.getByTestId("draft-editor");
  const original = await editor.inputValue();
  await editor.fill(`${original}\n\nI guarantee 100% results and can start today.`);
  await page.getByTestId("save-edit").click();
  // the edit goes back through verification and compliance: the guarantee is caught by policy P4
  const view = page.getByTestId("draft-view");
  await expect(view).toBeVisible({ timeout: 45_000 });
  // P4 rewrites the guarantee instead of sending it; the rest of the human edit is kept
  await expect(view).toContainText("aim for strong results and can start today");
  await expect(view).not.toContainText("guarantee 100% results");
  await expect(page.getByLabel("Draft")).toContainText("P4");
  await expect(page.getByTestId("approve")).toBeEnabled();
});
