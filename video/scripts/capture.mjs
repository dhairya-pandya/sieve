// Screenshot the live Sieve page (served by a local `sieve` API) for the video and for design review.
// Usage: node scripts/capture.mjs [base-url] [out-dir]
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";

const base = process.argv[2] || "http://127.0.0.1:8791";
const out = process.argv[3] || "public/shots";
mkdirSync(out, { recursive: true });
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const pages = [
  ["home", "/#/", "light"], ["home-dark", "/#/", "dark"], ["round", "/#/round/0", "light"],
  ["proposal", "/#/proposal/8", "light"], ["proposal-dark", "/#/proposal/8", "dark"],
  ["honeypot", "/#/round/1", "light"], ["redteam", "/#/redteam", "light"], ["about", "/#/about", "light"],
  ["mobile", "/#/", "light", { width: 390, height: 844 }],
];

const browser = await chromium.launch({ executablePath: chrome });
for (const [name, path, scheme, size] of pages) {
  const page = await browser.newPage({ viewport: size || { width: 1920, height: 1080 }, deviceScaleFactor: 1, colorScheme: scheme });
  await page.goto(base + path);
  await page.waitForFunction(() => !document.querySelector("#app")?.textContent.includes("Loading"), null, { timeout: 30000 });
  // The review list comes from an indexer that can briefly return nothing; reload until reviews show.
  for (let tries = 0; path.includes("proposal") && tries < 4 && !(await page.$(".review")); tries++) {
    await page.waitForTimeout(3000);
    await page.reload();
    await page.waitForFunction(() => !document.querySelector("#app")?.textContent.includes("Loading"), null, { timeout: 30000 });
  }
  if (path.includes("proposal")) {
    await page.waitForFunction(() => ![...document.querySelectorAll(".proof")].some((p) => p.textContent.includes("Checking")), null, { timeout: 60000 }).catch(() => {});
  }
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
  await page.close();
  console.log(name);
}
await browser.close();
