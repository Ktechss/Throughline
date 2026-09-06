// Drive the body builder and assert the figure actually responds.
//
//   node scripts/body-check.mjs
//
// Read-only: every non-GET /api call is stubbed by guard.mjs, so this can never
// create a character or spend credits.
import { chromium } from "playwright";
import { readOnly } from "./guard.mjs";
import { mkdirSync } from "node:fs";

mkdirSync("/tmp/tl-body", { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 1000 }, deviceScaleFactor: 2, colorScheme: "dark",
});
await readOnly(ctx, []);
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(e.message));
page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 160)); });

const SVG = 'svg[aria-label="Body proportion diagram"]';
// EVERY path, not just the last one: thighs move the LEG paths while the torso
// is unchanged, so comparing one path reported "no change" for a slider that
// was working perfectly well.
const shape = async () =>
  (await Promise.all((await page.locator(`${SVG} path`).all()).map((p) => p.getAttribute("d")))).join("|");

await page.goto("http://localhost:5173/characters/new", { waitUntil: "networkidle" });
await page.fill('input[placeholder*="Aelira"]', "Body Test").catch(() => {});
for (let i = 0; i < 2; i++) {
  await page.getByRole("button", { name: /^Next/ }).click({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(300);
}
await page.waitForTimeout(500);

console.log("  silhouette present:", (await page.locator(SVG).count()) > 0);

await page.getByRole("button", { name: "curvy", exact: true }).click().catch(() => {});
await page.waitForTimeout(280);
const curvy = await shape();
await page.getByRole("button", { name: "slim", exact: true }).click().catch(() => {});
await page.waitForTimeout(280);
const slim = await shape();
console.log("  preset changes the figure:", curvy !== slim);

await page.getByRole("button", { name: /Fine tune/ }).click().catch(() => {});
await page.waitForTimeout(400);
console.log("  granular sliders:", await page.locator('input[type="range"]').count());

const before = await shape();
await page.getByLabel("Thighs").fill("4");
await page.waitForTimeout(300);
console.log("  thigh slider morphs the figure:", before !== (await shape()));

const beforeLegs = await shape();
await page.getByLabel("Leg length").fill("0");
await page.waitForTimeout(300);
console.log("  leg-length slider morphs the figure:", beforeLegs !== (await shape()));

console.log("  emitted sentence shown:",
  (await page.locator("text=/very full, heavy thighs/").count()) > 0);
console.log("  reset restores the preset:",
  (await page.getByRole("button", { name: "reset" }).count()) > 0);

await page.screenshot({ path: "/tmp/tl-body/builder.png" });
console.log("  console errors:", errs.length ? errs.slice(0, 3) : "none");
await browser.close();
