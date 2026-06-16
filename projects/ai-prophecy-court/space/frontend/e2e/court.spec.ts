import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("completes a trial, reveals models, and prepares a verdict card", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      name: "Where confident AI predictions meet two equally confident comedians.",
    }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Dad joke" }).click();
  await page.getByRole("button", { name: "Convene Court" }).click();
  await expect(page.getByText("Model identity sealed")).toHaveCount(2);

  await page.getByRole("button", { name: "A wins" }).click();
  await expect(page.getByText("Model identities unsealed")).toBeVisible();
  await expect(page.getByText("nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16")).toBeVisible();

  await page.getByRole("button", { name: "Generate verdict card" }).click();
  await expect(page.getByRole("heading", { name: "Your verdict card is ready." })).toBeVisible();
  const download = page.getByRole("link", { name: "Download PNG" });
  await expect(download).toHaveAttribute(
    "download",
    "ai-prophecy-court-clement-delangue-a.png",
  );
  await expect(
    page.getByRole("img", { name: /Verdict card for Clement Delangue/ }),
  ).toBeVisible();
});

test("has no serious accessibility violations on primary routes", async ({ page }) => {
  for (const path of ["/", "/archive", "/people/clement-delangue"]) {
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = results.violations.filter(({ impact }) =>
      impact === "serious" || impact === "critical"
    );
    expect(serious, `${path} accessibility violations`).toEqual([]);
  }
});

test("supports keyboard navigation to the primary action", async ({ page }) => {
  await page.goto("/");

  const primaryAction = page.getByRole("button", { name: "Convene Court" });
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (await primaryAction.evaluate((element) => element === document.activeElement)) {
      break;
    }
    await page.keyboard.press("Tab");
  }

  await expect(primaryAction).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Evidence admitted")).toBeVisible();
});
