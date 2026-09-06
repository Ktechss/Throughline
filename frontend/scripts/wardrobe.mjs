// Record what wardrobe delete fires — nothing is allowed through.
import { chromium } from "playwright";
const b = await chromium.launch();
const ctx = await b.newContext({viewport:{width:1600,height:1000},colorScheme:"dark"});
const seen = []; const errs = [];
await ctx.route("**/api/**", (r) => {
  const q = r.request();
  if (q.method() === "GET") return r.continue();
  seen.push(`${q.method()} ${new URL(q.url()).pathname}`);
  return r.fulfill({status:200, contentType:"application/json", body:"{}"});
});
const p = await ctx.newPage();
p.on("pageerror", e => errs.push("PAGEERROR " + e.message.slice(0,160)));
p.on("dialog", d => { console.log("  native dialog:", d.message().slice(0,60)); d.accept(); });

await p.goto("http://127.0.0.1:5173/studio?char=kiara&tab=shoot",{waitUntil:"domcontentloaded"});
await p.locator('text=/12 of 110/').waitFor({timeout:20000}).catch(()=>{});
await p.waitForTimeout(1500);

// hover the first outfit tile to reveal its controls, then look for a delete
const tile = p.locator('[class*="aspect"]').first();
await tile.hover();
await p.waitForTimeout(400);
const btns = await tile.locator("button").count();
console.log("buttons revealed on hover over an outfit tile:", btns);
for (let i = 0; i < btns; i++) {
  const t = (await tile.locator("button").nth(i).getAttribute("title")) ||
            (await tile.locator("button").nth(i).getAttribute("aria-label")) || "(none)";
  console.log("   button", i, "title/label =", t);
}
// try the delete affordance
const del = tile.locator('button[title*="elete"], button[aria-label*="elete"]').first();
if (await del.count()) {
  await del.click();
  await p.waitForTimeout(1200);
  // a confirm dialog may appear
  const confirmBtn = p.getByRole("button", { name: /^(Delete|Delete it|Confirm)$/ });
  if (await confirmBtn.count()) { console.log("  confirm dialog shown"); await confirmBtn.first().click(); }
  await p.waitForTimeout(1200);
} else console.log("  NO delete affordance found on the tile");
console.log("fired:", seen.length ? seen.join(" | ") : "NOTHING");
if (errs.length) console.log("errors:", [...new Set(errs)].join(" | "));
await b.close();
