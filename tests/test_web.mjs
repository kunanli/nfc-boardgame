// 驗證 docs/index.html 內嵌的 JS 規則引擎，與 Python 版邏輯一致。
// 執行： node tests/test_web.mjs
import { readFileSync } from "node:fs";
import assert from "node:assert";

const html = readFileSync(new URL("../docs/index.html", import.meta.url), "utf8");
const script = html.split("<script>")[1].split("</script>")[0];
// 只取「畫面」之前的引擎部分（避開 DOM/localStorage 相依）
const engineSrc = script.split("// 畫面")[0];

// 把要用到的函式匯出到 sandbox
const factory = new Function(engineSrc + `
  return { fresh, tap, startAdventure, leaderboard, CARDS };
`);
const { fresh, tap, startAdventure, leaderboard } = factory();

const WARRIOR="04A1B2C3", RANGER="04A1B2C4", MAGE="04A1B2C6";
const GOBLIN="04D0E0F1", WOLF="04D0E0F2", DRAGON="04D0E0FF", RUNE="04C0FFEE2";

let pass = 0;
function t(name, fn){ fn(); console.log("  ✓", name); pass++; }

// 玩家：加入、重複、未登錄
t("join / duplicate / unknown", ()=>{
  const s = fresh();
  assert.equal(tap(s, WARRIOR).event, "player_joined");
  assert.equal(tap(s, WARRIOR).event, "duplicate");
  assert.equal(tap(s, "DEADBEEF").event, "unknown_card");
  assert.equal(s.players.length, 1);
});

// 規則：只有輪到的人能出手
t("not your turn is blocked", ()=>{
  const s = fresh();
  tap(s, WARRIOR); tap(s, MAGE); startAdventure(s);
  tap(s, GOBLIN);
  assert.equal(tap(s, MAGE).event, "not_your_turn"); // seat1 還沒輪到
});

// 規則：尾刀者獨得賞金
t("last hit takes reward", ()=>{
  const s = fresh();
  tap(s, WARRIOR); tap(s, MAGE); startAdventure(s);
  tap(s, GOBLIN);                       // hp12
  assert.equal(tap(s, WARRIOR).event, "attack");   // 12-6=6
  assert.equal(tap(s, MAGE).event, "last_hit");    // 6-10 補刀
  assert.equal(s.players[1].gold, 5);
  assert.equal(s.players[0].gold, 0);
});

// 規則：反擊 + 撤退扣金
t("counter + knockout penalty", ()=>{
  const s = fresh();
  tap(s, MAGE); startAdventure(s);
  // 先補刀哥布林賺 5
  tap(s, GOBLIN); tap(s, MAGE); tap(s, MAGE);
  assert.equal(s.players[0].gold, 5);
  // 再被巨龍打倒 -> 撤退滿血、扣 3
  tap(s, DRAGON);
  let ko = false;
  for(let i=0;i<12;i++){ const r = tap(s, MAGE); if(/撤退回城/.test(r.message)){ ko=true; break; } }
  assert.ok(ko);
  assert.equal(s.players[0].hp, s.players[0].maxHp);
  assert.equal(s.players[0].gold, 2); // 5 - 3
  assert.equal(s.players[0].kos, 1);
});

// 道具：符文加攻並消耗回合
t("rune buffs atk and uses turn", ()=>{
  const s = fresh();
  tap(s, WARRIOR); tap(s, RANGER); startAdventure(s);
  assert.equal(tap(s, RUNE).event, "item_used");
  assert.equal(s.players[0].atk, 9);   // 6+3
  assert.equal(s.turnIndex, 1);        // 換人
});

// 目標：打倒 boss 結束、金幣最高者贏（與 Python 同一場計算）
t("boss kill ends game, mage wins with 30", ()=>{
  const s = fresh();
  tap(s, WARRIOR); tap(s, MAGE); startAdventure(s);
  tap(s, DRAGON);
  const names = { "04A1B2C3":WARRIOR, "04A1B2C6":MAGE };
  let guard = 0;
  while(s.phase === "adventure" && s.current && guard++ < 100){
    const cur = s.players[s.turnIndex].uid;
    tap(s, cur);
  }
  assert.equal(s.phase, "over");
  const board = leaderboard(s);
  assert.equal(board[0].name, s.winner);
  assert.equal(board[0].gold, 30);
  assert.equal(s.winner, "法師 · 薇拉");
});

// 目標：囤金者可反超補到 boss 的人
t("hoarder beats the boss killer", ()=>{
  const s = fresh();
  tap(s, WARRIOR); tap(s, MAGE); startAdventure(s);
  s.players[0].gold = 100;
  tap(s, DRAGON);
  let guard = 0;
  while(s.phase === "adventure" && s.current && guard++ < 100){
    tap(s, s.players[s.turnIndex].uid);
  }
  assert.equal(s.phase, "over");
  assert.equal(s.winner, "戰士 · 阿爾");
});

console.log(`\nOK — ${pass} 個 JS 引擎測試全數通過`);
