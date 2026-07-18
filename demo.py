"""互動式示範：不需要真的 NFC 硬體，用「輸入 UID」模擬刷卡走完一局。

執行：
    python3 demo.py            # 跑一場預設腳本（自動示範）
    python3 demo.py -i         # 互動模式，手動輸入卡片 UID 當作刷卡
"""
from __future__ import annotations

import sys

from game.cards import CardDB
from game.engine import Game, Phase

# 方便示範用的別名 -> UID
ALIAS = {
    "戰士": "04A1B2C3", "遊俠": "04A1B2C4", "牧師": "04A1B2C5", "法師": "04A1B2C6",
    "哥布林": "04D0E0F1", "狼群": "04D0E0F2", "石魔像": "04D0E0F3", "巨龍": "04D0E0FF",
    "藥水": "04C0FFEE1", "符文": "04C0FFEE2",
}


def resolve(token: str) -> str:
    return ALIAS.get(token, token)


def show(prefix: str, r) -> None:
    mark = "✓" if r.ok else "✗"
    print(f"  {mark} [{prefix}] {r.message}")


def scripted(g: Game) -> None:
    print("=== 組隊 ===")
    for name in ("戰士", "遊俠", "法師"):
        show("刷卡", g.tap(resolve(name)))
    show("開始", g.start_adventure())

    print("\n=== 冒險：搶尾刀奪寶 ===")
    # 一路輪替，直到最終王倒下
    plan = ["哥布林", "狼群", "石魔像", "巨龍"]
    for monster in plan:
        if g.phase != Phase.ADVENTURE:
            break
        print(f"\n-- 翻出 {monster} --")
        show("翻怪", g.tap(resolve(monster)))
        while g.phase == Phase.ADVENTURE and g.current is not None:
            current = g.state()["turn"]
            turn_uid = next(p.hero.uid for p in g.players if p.name == current)
            show(f"{current} 出手", g.tap(turn_uid))

    print("\n=== 結算 ===")
    st = g.state()
    print(f"  最終王擊殺者贏得 boss 賞金，總金幣結算：")
    for i, row in enumerate(st["leaderboard"], 1):
        crown = " 👑" if row["name"] == st["winner"] else ""
        print(f"    {i}. {row['name']}：{row['gold']} 金幣（撤退 {row['kos']} 次）{crown}")
    print(f"\n  🏆 冠軍：{st['winner']}")


def interactive(g: Game) -> None:
    print("互動模式：輸入卡片別名或 UID 當作刷卡。指令：start / state / quit")
    print("英雄：戰士 遊俠 牧師 法師 ｜ 怪物：哥布林 狼群 石魔像 巨龍 ｜ 道具：藥水 符文\n")
    while True:
        try:
            token = input("刷卡> ").strip()
        except EOFError:
            break
        if not token:
            continue
        if token in ("quit", "q", "exit"):
            break
        if token == "start":
            show("開始", g.start_adventure())
            continue
        if token == "state":
            import json
            print(json.dumps(g.state(), ensure_ascii=False, indent=2))
            continue
        show("刷卡", g.tap(resolve(token)))
        if g.phase == Phase.OVER:
            print(f"\n🏆 遊戲結束，冠軍：{g.winner}")
            break


def main() -> None:
    g = Game(CardDB.load())
    if "-i" in sys.argv or "--interactive" in sys.argv:
        interactive(g)
    else:
        scripted(g)


if __name__ == "__main__":
    main()
