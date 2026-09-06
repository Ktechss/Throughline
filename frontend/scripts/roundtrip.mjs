// Real writes, on ONE item, verified in the UI. Restored by the caller.
import { chromium } from "playwright";
const b = await chromium.launch();
const p = await (await b.newContext({viewport:{width:1600,height:1000},colorScheme:"dark"})).newPage();
const errs = [];
p.on("pageerror", e => errs.push("PAGEERROR " + e.message.slice(0,200)));
p.on("console", m => { if (m.type()==="error") errs.push("CONSOLE " + m.text().slice(0,200)); });
p.on("response", r => { if (r.url().includes("/api/") && r.status() >= 400)
  errs.push(`HTTP ${r.status()} ${new URL(r.url()).pathname}`); });

await p.goto("http://127.0.0.1:5173/studio?char=kiara&tab=review",{waitUntil:"domcontentloaded"});
await p.waitForTimeout(4000);

// filter to Unmarked so we act on a known-unmarked card
await p.getByRole("radio", { name: /Unmarked/ }).click().catch(async () =>
  p.getByRole("button", { name: /Unmarked/ }).click());
await p.waitForTimeout(900);

const card = p.locator('[class*="group"]:has(button:text-is("approve"))').first();
console.log("APPROVE button label before:", await card.getByRole("button",{name:/approve/}).textContent());
await card.getByRole("button", { name: /^approve$/ }).click();
await p.waitForTimeout(2500);
const after = await p.locator('button:text-is("approved")').count();
console.log("cards now showing 'approved':", after);
console.log("Approved chip count:", (await p.getByRole("button",{name:/^Approved/}).textContent().catch(()=> "n/a")));
if (errs.length) console.log("ERRORS:", [...new Set(errs)].join(" | "));
else console.log("no console/network errors");
await b.close();
