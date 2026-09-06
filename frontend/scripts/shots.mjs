// Screenshot every screen, so design decisions stop being made blind.
//
//   node scripts/shots.mjs [outDir]
//
// Captures full-page PNGs at desktop width, plus a couple of narrow ones, and
// reports any console error or failed request it saw on the way — a page that
// looks fine in a screenshot can still be throwing.
import { chromium } from "playwright";
import { readOnly } from "./guard.mjs";

const BLOCKED = [];
const withGuard = async (b, opts) => {
  const c = await b.newContext(opts);
  await readOnly(c, BLOCKED);
  return c;
};
import { mkdirSync } from "node:fs";
import path from "node:path";

const OUT = process.argv[2] || "/tmp/tl-shots";
const BASE = process.env.BASE || "http://127.0.0.1:5173";

const SHOTS = [
  { name: "01-landing", url: "/" },
  { name: "02-create-step1", url: "/characters/new" },
  { name: "03-create-step2", url: "/characters/new", steps: 1 },
  { name: "04-create-step3", url: "/characters/new", steps: 2 },
  { name: "05-create-step5", url: "/characters/new", steps: 4 },
  { name: "06-studio-shoot", url: "/studio?char=kiara&tab=shoot" },
  { name: "07-studio-bio", url: "/studio?char=kiara&tab=bio" },
  { name: "08-studio-calibrate", url: "/studio?char=kiara&tab=calibrate" },
  { name: "09-studio-review", url: "/studio?char=kiara&tab=review" },
  { name: "10-studio-motion", url: "/studio?char=kiara&tab=motion" },
  { name: "11-scenes", url: "/collaborate" },
  { name: "12-settings", url: "/settings" },
  { name: "13-notfound", url: "/nonsense" },
];

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const problems = [];

for (const vp of [{ w: 1440, h: 900, tag: "" }, { w: 900, h: 900, tag: "-narrow" }]) {
  const ctx = await browser.newContext({
    viewport: { width: vp.w, height: vp.h },
    deviceScaleFactor: 2,
    colorScheme: "dark",
  });
  const list = vp.tag ? SHOTS.filter((s) => ["01-landing", "06-studio-shoot", "09-studio-review"].includes(s.name)) : SHOTS;

  for (const s of list) {
    const page = await ctx.newPage();
    const errs = [];
    page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 200)); });
    page.on("pageerror", (e) => errs.push(`PAGEERROR ${e.message.slice(0, 200)}`));
    page.on("requestfailed", (r) => errs.push(`REQFAIL ${r.url().slice(0, 120)}`));
    try {
      await page.goto(BASE + s.url, { waitUntil: "networkidle", timeout: 30000 });
      // Walk the wizard forward when the shot asks for a later step.
      if (s.steps) {
        await page.fill('input[placeholder*="Aelira"]', "Screenshot Test").catch(() => {});
        for (let i = 0; i < s.steps; i++) {
          await page.getByRole("button", { name: /^Next/ }).click({ timeout: 5000 }).catch(() => {});
          await page.waitForTimeout(250);
        }
      }
      await page.waitForTimeout(600);
      await page.screenshot({ path: path.join(OUT, `${s.name}${vp.tag}.png`), fullPage: true });
      const label = `${s.name}${vp.tag}`;
      if (errs.length) problems.push(`${label}: ${[...new Set(errs)].slice(0, 4).join(" | ")}`);
      console.log(`  ${errs.length ? "!" : "✓"} ${label}`);
    } catch (e) {
      console.log(`  ✗ ${s.name}${vp.tag} — ${e.message.split("\n")[0]}`);
      problems.push(`${s.name}${vp.tag}: ${e.message.split("\n")[0]}`);
    }
    await page.close();
  }
  await ctx.close();
}

await browser.close();
console.log(`\nwrote to ${OUT}`);
if (problems.length) {
  console.log("\nPROBLEMS SEEN:");
  for (const p of problems) console.log("  -", p);
} else {
  console.log("\nno console errors or failed requests");
}
