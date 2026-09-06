// A SCREENSHOT RUN MUST NOT BE ABLE TO CHANGE ANYTHING.
//
// It could, and it did: a scripted pass over the Review tab fired
// POST /api/runs/mark-bulk and approved 168 shots, overwriting the `mark`
// verdicts — which are the one thing in this project a human has to supply and
// nothing can regenerate. The marks were restored from a backup, but the lesson
// is that "I only meant to look" is not a property of a browser session unless
// something enforces it.
//
// So the observer is now read-only by construction: every non-GET request to
// /api is aborted before it leaves the page, and the run reports anything it
// blocked so a silently-broken interaction cannot masquerade as a clean pass.
export async function readOnly(ctx, blocked = []) {
  await ctx.route("**/api/**", (route) => {
    const req = route.request();
    if (req.method() === "GET") return route.continue();
    blocked.push(`${req.method()} ${new URL(req.url()).pathname}`);
    // 200 with an empty body: an aborted request surfaces as a network error
    // and buries the page in error banners, which is not what we came to see.
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  return blocked;
}
