// 真瀏覽器端對端測試：模擬 iPhone「碰卡開網址」的實際流程 ——
// 每次以 ?tap=UID 導頁，驗證狀態透過 localStorage 累積、去參數防重複。
// 執行： node tests/test_browser.mjs
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
const require = createRequire("/opt/node22/lib/node_modules/");
const { chromium } = require("/opt/node22/lib/node_modules/playwright");

const html = readFileSync(new URL("../docs/index.html", import.meta.url), "utf8");
const server = createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(html);
});
await new Promise(r => server.listen(0, r));
const base = `http://127.0.0.1:${server.address().port}/`;

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
const page = await browser.newPage();

async function go(q){ await page.goto(base + q); await page.waitForFunction(() => document.getElementById("app")?.innerText?.length > 0); return page.locator("#app").innerText(); }

let ok = true;
function check(cond, label){ console.log((cond?"  ✓ ":"  ✗ ")+label); if(!cond) ok=false; }

try {
  await go("?reset=1");
  let m = await go("?tap=04A1B2C3"); check(/阿爾 加入/.test(m), "碰戰士卡 → 加入");
  m = await go("?tap=04A1B2C6");     check(/薇拉 加入/.test(m), "碰法師卡 → 加入（狀態有累積）");
  m = await go("?start=1");          check(/冒險開始/.test(m), "開始冒險");
  m = await go("?tap=04D0E0F1");     check(/哥布林/.test(m), "碰怪物卡 → 翻出哥布林");
  m = await go("?tap=04A1B2C3");     check(/砍出|補刀/.test(m), "戰士出手");

  // 去參數防重複：出手後網址應已無 query
  const url = page.url();
  check(!url.includes("?"), "出手後網址已去掉參數（重整不會重複觸發）");

  // localStorage 真的有存
  const stored = await page.evaluate(() => localStorage.getItem("nfc_boardgame_state_v1"));
  check(stored && JSON.parse(stored).players.length === 2, "狀態存進 localStorage");

  // 設定頁列出每張卡的網址
  await page.goto(base + "?view=setup");
  const setup = await page.content();
  check(setup.includes("?tap=04D0E0FF"), "設定頁列出巨龍卡網址");
} finally {
  await browser.close();
  server.close();
}
console.log(ok ? "\nOK — 瀏覽器端對端流程正常" : "\n有測試失敗");
process.exit(ok ? 0 : 1);
