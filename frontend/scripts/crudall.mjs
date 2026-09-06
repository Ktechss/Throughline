// Every destructive/mutating affordance, exercised with writes BLOCKED.
// Reports: does the control exist, does it fire, does it fire the right call.
import { chromium } from "playwright";
const b = await chromium.launch();
const ctx = await b.newContext({viewport:{width:1600,height:1100},colorScheme:"dark"});
const seen = [], errs = [];
await ctx.route("**/api/**", (r) => {
  const q = r.request();
  if (q.method() === "GET") return r.continue();
  seen.push(`${q.method()} ${new URL(q.url()).pathname}`);
  return r.fulfill({status:200, contentType:"application/json", body:"{}"});
});
const p = await ctx.newPage();
p.on("pageerror", e => errs.push("PAGEERROR " + e.message.slice(0,120)));
p.on("dialog", d => d.accept());

const go = async (url, ready) => {
  await p.goto("http://127.0.0.1:5173"+url, {waitUntil:"domcontentloaded"});
  if (ready) await p.locator(ready).first().waitFor({timeout:25000}).catch(()=>{});
  await p.waitForTimeout(1200);
};
const T = async (name, fn) => {
  seen.length = 0; errs.length = 0;
  let note = "";
  try { await fn(); } catch (e) { note = " (no control found)"; }
  await p.waitForTimeout(900);
  const conf = p.getByRole("button", { name: /^(Delete|Delete her|Remove|Reset|Wipe|Clean up|Confirm|Save|Add|Rename)$/ });
  if (await conf.count()) { await conf.first().click().catch(()=>{}); await p.waitForTimeout(700); }
  const fired = seen.length ? seen.join(" | ") : "NOTHING" + note;
  console.log(`  ${name.padEnd(26)} ${fired}${errs.length ? "  ERR:"+errs[0] : ""}`);
};

console.log("### REVIEW");
await go("/studio?char=kiara&tab=review", 'button:text-is("approve")');
await T("approve", () => p.locator('button:text-is("approve")').first().click());
await T("reject",  () => p.locator('button:text-is("reject")').first().click());
await T("delete image", () => p.locator('[class*="group"] button[title*="elete"], [class*="group"] svg.lucide-trash2').first().click());
await T("export gold set", () => p.getByRole("button",{name:/Export gold set/}).click());
await T("clean up images", () => p.getByRole("button",{name:/Clean up images/}).click());

console.log("### SHOOT / WARDROBE / NAILS");
await go("/studio?char=kiara&tab=shoot", 'text=/of 110/');
await T("delete outfit", async () => { const t=p.locator('[class*="aspect"]').first();
  await t.hover(); await p.waitForTimeout(300); await t.locator('button[aria-label*="Delete"]').first().click(); });

console.log("### BIO");
await go("/studio?char=kiara&tab=bio", 'text=Identity reference');
await T("set BIO ref", () => p.getByRole("button",{name:/set\s*BIO/}).first().click());
await T("→ gallery", () => p.getByRole("button",{name:/→ gal/}).first().click());
await T("delete ref", () => p.locator('button:has(svg.lucide-trash2)').first().click());

console.log("### CHARACTERS");
await go("/", 'text=Recent shots');
await T("rename character", async () => { await p.getByRole("button",{name:/More/}).first().click();
  await p.waitForTimeout(300); await p.getByRole("button",{name:/Rename/}).click(); });

console.log("### SETTINGS");
await go("/settings", 'text=Image providers');
await T("toggle provider", () => p.locator('button[title="Enable / disable"]').first().click());
await T("reorder provider", () => p.locator('section:has-text("Image providers") button:has(svg.lucide-arrow-down)').first().click());
await T("add an era", () => p.getByRole("button",{name:/Add an era/}).click());
await b.close();
