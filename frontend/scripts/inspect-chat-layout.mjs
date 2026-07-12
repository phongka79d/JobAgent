/**
 * Deterministic viewport inspection for Plan 3 chat shell.
 * Loads the Vite dev app and checks empty/loading/composer structure at
 * desktop (1440x900) and mobile (390x844) without relying on a live API.
 */
import { chromium } from "playwright";

const BASE = process.env.CHAT_INSPECT_URL ?? "http://127.0.0.1:5173/";

async function inspectViewport(browser, { width, height, label }) {
  const page = await browser.newPage({ viewport: { width, height } });

  // History/profile hydrate fail without backend; shell must still show chat + sidebar.
  await page.route("**/api/chat/history**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ messages: [] }),
    });
  });
  await page.route("**/api/profile**", async (route) => {
    if (route.request().url().includes("/api/profile/cv")) {
      await route.fulfill({ status: 404, body: "NO_ACTIVE_CV" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        state: "none",
        profile: null,
        preferences: null,
        active_attachment: null,
      }),
    });
  });

  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForSelector('[data-testid="chat-app-shell"], [data-testid="chat-empty-state"], [role="textbox"]', {
    timeout: 15_000,
  });

  // Prefer empty state after successful hydrate mock.
  await page.waitForTimeout(300);

  const bodyText = await page.locator("body").innerText();
  const box = await page.locator("body").boundingBox();
  const textbox = page.getByRole("textbox");
  const textboxCount = await textbox.count();
  const emptyVisible = await page.getByText(/Start a conversation/i).count();
  const sidebarVisible = await page.locator('[data-testid="profile-sidebar"]').count();
  const landingPlaceholder = /product workflows are intentionally disabled/i.test(
    bodyText,
  );
  const prohibited =
    /sk-live|Authorization:|Traceback|raw_args|shopaikey/i.test(bodyText);

  // Check composer and empty/heading do not overflow body width.
  let overflow = false;
  if (box) {
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    overflow = scrollWidth > clientWidth + 2;
  }

  const result = {
    label,
    width,
    height,
    textboxCount,
    emptyVisible: emptyVisible > 0,
    sidebarVisible: sidebarVisible > 0,
    landingPlaceholder,
    prohibited,
    overflow,
    sample: bodyText.slice(0, 200).replace(/\s+/g, " "),
  };

  await page.close();
  return result;
}

const browser = await chromium.launch({ headless: true });
try {
  const desktop = await inspectViewport(browser, {
    width: 1440,
    height: 900,
    label: "desktop-1440x900",
  });
  const mobile = await inspectViewport(browser, {
    width: 390,
    height: 844,
    label: "mobile-390x844",
  });

  const results = [desktop, mobile];
  console.log(JSON.stringify(results, null, 2));

  const failed = results.filter(
    (r) =>
      r.landingPlaceholder ||
      r.prohibited ||
      r.overflow ||
      r.textboxCount < 1 ||
      !r.emptyVisible,
  );
  if (failed.length > 0) {
    console.error("INSPECT_FAIL", failed.map((f) => f.label).join(", "));
    process.exit(1);
  }
  console.log("INSPECT_PASS");
} finally {
  await browser.close();
}
