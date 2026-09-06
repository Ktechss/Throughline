// Click things and RECORD what request they fire, without letting any write
// through. Answers "is the button wired?" separately from "does the API work?".
import { chromium } from "playwright";
const b = await chromium.launch();
const ctx = await b.newContext({viewport:{width:1600,height:1000},colorScheme:"dark"});
const seen = [];
await ctx.route("**/api/**", (r) => {
  const q = r.request();
  if (q.method() === "GET") return r.continue();
  seen.push(`${q.method()} ${new URL(q.url()).pathname}  body=${(q.postData()||"").slice(0,120)}`);
  return r.fulfill({ status: 200, contentType: "application/json", body: "{}" });
});
const p = await ctx.newPage();
const errs = [];
p.on("pageerror", e => errs.push("PAGEERROR " + e.message.slice(0,160)));
p.on("console", m => { if (m.type()==="error") errs.push("CONSOLE " + m.text().slice(0,160)); });

const step = async (name, fn) => {
  seen.length = 0; errs.length = 0;
  try { await fn(); } catch (e) { console.log(`  ${name}: THREW ${e.message.split("\n")[0].slice(0,90)}`); }
  await p.waitForTimeout(700);
  console.log(`  ${name}\n     fired: ${seen.length ? seen.join(" | ") : "NOTHING"}`);
  if (errs.length) console.log(`     errors: ${[...new Set(errs)].join(" | ")}`);
};

console.log("### REVIEW");
await p.goto("http://127.0.0.1:5173/studio?char=kiara&tab=review",{waitUntil:"networkidle"});
await p.waitForTimeout(1500);
await step("approve on a card", () => p.getByRole("button",{name:/^approve$/}).first().click());
await step("reject on a card",  () => p.getByRole("button",{name:/^reject$/}).first().click());

console.log("\n### WARDROBE (shoot tab)");
await p.goto("http://127.0.0.1:5173/studio?char=kiara&tab=shoot",{waitUntil:"networkidle"});
await p.waitForTimeout(1800);
await step("select an outfit", () => p.locator('img[alt], [class*="aspect"]').nth(0).click());

await b.close();
