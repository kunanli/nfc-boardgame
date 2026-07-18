"""規則引擎 / 服務端裁判 —— 競爭模式「搶尾刀奪寶」。

核心概念：整套遊戲只有一個入口 —— `Game.tap(uid)`，模擬玩家在讀卡機上刷卡。
服務端依「當前階段 + 卡片種類 + 輪到誰」判定這一刷代表什麼，並結算戰鬥與勝負。

玩法定位：大家「組隊」在同一個地城冒險打同一批怪，但彼此是對手 ——
誰對怪物打出最後一擊（尾刀）就獨得該怪的獎勵。最終王倒下時，金幣最多者獲勝。

三個最小單位：
  規則(rules)   -> 輪流出手、尾刀奪寶、怪物反擊、撤退懲罰
  目標(goal)    -> 打倒最終王時，累積金幣最多的玩家獲勝
  玩家(players) -> 各持一張英雄卡，刷卡加入、輪流刷卡出手、各自計分
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from .cards import CardDB
from .models import Monster, Player


class Phase(str, Enum):
    LOBBY = "lobby"          # 組隊中，等待玩家刷英雄卡
    ADVENTURE = "adventure"  # 冒險中，翻怪物、輪流出手
    OVER = "over"            # 最終王已倒，比金幣分勝負


@dataclass
class TapResult:
    """每次刷卡的判定結果，回傳給前端 / 讀卡機顯示。"""
    ok: bool
    event: str
    message: str
    phase: str
    detail: dict = field(default_factory=dict)


class Game:
    MIN_PLAYERS = 1     # 最小單位測試允許 1 人；正式建議 2~4 人
    KO_PENALTY = 3      # 被打倒撤退回城，扣除的金幣

    def __init__(self, db: CardDB):
        self.db = db
        self.phase = Phase.LOBBY
        self.players: List[Player] = []
        self.turn_index = 0                       # 輪到哪個座位出手
        self.current: Optional[Monster] = None    # 桌面上待打的怪物
        self.slain: List[Tuple[str, str]] = []    # (怪物名, 尾刀者名)
        self.winner: Optional[str] = None
        self.log: List[str] = []

    # ---------- 單一入口：刷卡 ----------
    def tap(self, uid: str) -> TapResult:
        if not self.db.has(uid):
            return self._result(False, "unknown_card",
                                 f"未登錄的卡片 {uid}（空白卡？請先在 cards.json 登錄）")
        kind = self.db.type_of(uid)

        if self.phase == Phase.LOBBY:
            if kind == "hero":
                return self._join(uid)
            return self._result(False, "wrong_phase", "組隊階段只能刷英雄卡加入。")

        if self.phase == Phase.ADVENTURE:
            if kind == "monster":
                return self._reveal(uid)
            if kind == "hero":
                return self._attack(uid)
            if kind == "item":
                return self._use_item(uid)

        return self._result(False, "game_over", "遊戲已結束，比比金幣看誰贏了。")

    # ---------- 組隊 ----------
    def _join(self, uid: str) -> TapResult:
        if any(p.hero.uid == uid for p in self.players):
            return self._result(False, "duplicate", "這張英雄卡已在隊伍中。")
        hero = self.db.make_hero(uid)
        player = Player(hero=hero, seat=len(self.players))
        self.players.append(player)
        self.log.append(f"{hero.name} 加入")
        return self._result(True, "player_joined",
                            f"{hero.name} 加入（第 {len(self.players)} 位）",
                            detail={"party_size": len(self.players), "seat": player.seat})

    def start_adventure(self) -> TapResult:
        """由主持人觸發：結束組隊、開始冒險，由座位 0 先手。"""
        if self.phase != Phase.LOBBY:
            return self._result(False, "wrong_phase", "現在不是組隊階段。")
        if len(self.players) < self.MIN_PLAYERS:
            return self._result(False, "not_enough_players",
                                f"至少需要 {self.MIN_PLAYERS} 位玩家。")
        self.phase = Phase.ADVENTURE
        self.turn_index = 0
        self.log.append(f"冒險開始，{len(self.players)} 人競逐戰利品")
        return self._result(True, "adventure_started",
                            f"冒險開始！輪到 {self._current_player().name}，翻一張怪物卡開打。",
                            detail={"turn": self._current_player().name})

    # ---------- 翻出怪物 ----------
    def _reveal(self, uid: str) -> TapResult:
        if self.current is not None:
            return self._result(False, "monster_present",
                                f"桌上還有 {self.current.name}（HP {self.current.hp}），先解決它。")
        self.current = self.db.make_monster(uid)
        m = self.current
        return self._result(True, "monster_revealed",
                            f"出現了 {m.name}！HP {m.hp}、攻擊 {m.atk}、賞金 {m.reward}。"
                            f"輪到 {self._current_player().name} 出手。",
                            detail={"monster": m.name, "hp": m.hp, "atk": m.atk,
                                    "reward": m.reward, "boss": m.boss,
                                    "turn": self._current_player().name})

    # ---------- 出手：搶尾刀 ----------
    def _attack(self, uid: str) -> TapResult:
        player = next((p for p in self.players if p.hero.uid == uid), None)
        if player is None:
            return self._result(False, "not_in_party", "這張英雄卡沒有加入隊伍。")
        if self.current is None:
            return self._result(False, "no_monster", "桌面上沒有怪物，先翻一張怪物卡。")
        if player.seat != self.turn_index:
            return self._result(False, "not_your_turn",
                                f"還沒輪到你，現在是 {self._current_player().name} 的回合。")

        monster = self.current
        dmg = player.hero.atk
        monster.take_damage(dmg)
        detail = {"attacker": player.name, "damage": dmg, "monster_hp": monster.hp}

        # 尾刀！獨得獎勵
        if not monster.alive:
            player.gold += monster.reward
            self.slain.append((monster.name, player.name))
            self.log.append(f"{player.name} 對 {monster.name} 補刀，獨得 {monster.reward} 金幣")
            detail.update({"last_hit": True, "reward": monster.reward, "gold": player.gold})
            was_boss = monster.boss
            self.current = None
            if was_boss:
                return self._finish(player, monster, detail)
            self._advance_turn()
            detail["turn"] = self._current_player().name
            return self._result(True, "last_hit",
                                f"{player.name} 補刀擊殺 {monster.name}，獨得 {monster.reward} 金幣"
                                f"（共 {player.gold}）！輪到 {self._current_player().name}。",
                                detail=detail)

        # 沒打死：怪物反擊出手者
        monster_dmg = monster.atk
        player.hero.take_damage(monster_dmg)
        detail.update({"counter_damage": monster_dmg, "attacker_hp": player.hero.hp})
        msg = (f"{player.name} 砍出 {dmg} 傷害（{monster.name} 剩 {monster.hp}），"
               f"被反擊 {monster_dmg}（剩 HP {player.hero.hp}）。")

        if not player.hero.alive:
            # 撤退回城：滿血復活，但扣金幣懲罰貪刀
            lost = min(self.KO_PENALTY, player.gold)
            player.hero.hp = player.hero.max_hp
            player.gold -= lost
            player.kos += 1
            detail.update({"knocked_out": True, "gold_lost": lost, "gold": player.gold})
            self.log.append(f"{player.name} 被 {monster.name} 打倒，撤退回城，損失 {lost} 金幣")
            msg = (f"{player.name} 被 {monster.name} 打倒！撤退回城滿血復活，"
                   f"損失 {lost} 金幣（剩 {player.gold}）。")

        self._advance_turn()
        detail["turn"] = self._current_player().name
        return self._result(True, "attack", msg + f" 輪到 {self._current_player().name}。",
                            detail=detail)

    # ---------- 道具：消耗自己的回合使用 ----------
    def _use_item(self, uid: str) -> TapResult:
        player = self._current_player()
        c = self.db.raw(uid)
        effect = c.get("effect")
        amount = c.get("amount", 0)
        if effect == "heal":
            before = player.hero.hp
            player.hero.restore(amount)
            gained = player.hero.hp - before
            self._advance_turn()
            return self._result(True, "item_used",
                                f"{player.name} 使用 {c['name']}，回復 {gained} 點"
                                f"（HP {player.hero.hp}）。輪到 {self._current_player().name}。",
                                detail={"turn": self._current_player().name})
        if effect == "buff_atk":
            player.hero.atk += amount
            self._advance_turn()
            return self._result(True, "item_used",
                                f"{player.name} 使用 {c['name']}，攻擊力永久 +{amount}"
                                f"（現為 {player.hero.atk}）。輪到 {self._current_player().name}。",
                                detail={"turn": self._current_player().name})
        return self._result(False, "unknown_item", f"未知道具效果：{effect}")

    # ---------- 結算：最終王倒下 ----------
    def _finish(self, killer: Player, boss: Monster, detail: dict) -> TapResult:
        self.phase = Phase.OVER
        board = self.leaderboard()
        self.winner = board[0]["name"]
        detail.update({"leaderboard": board, "winner": self.winner, "boss_killer": killer.name})
        return self._result(True, "boss_defeated",
                            f"{killer.name} 對最終王 {boss.name} 補刀擊殺！"
                            f"金幣結算：{self.winner} 以 {board[0]['gold']} 金幣獲勝。",
                            detail=detail)

    # ---------- 輔助 ----------
    def _current_player(self) -> Player:
        return self.players[self.turn_index]

    def _advance_turn(self) -> None:
        if self.players:
            self.turn_index = (self.turn_index + 1) % len(self.players)

    def leaderboard(self) -> List[dict]:
        """依金幣排名；同分時撤退次數少者優先，再依座位。"""
        ranked = sorted(
            self.players,
            key=lambda p: (-p.gold, p.kos, p.seat or 0),
        )
        return [{"name": p.name, "gold": p.gold, "kos": p.kos, "seat": p.seat}
                for p in ranked]

    def _result(self, ok: bool, event: str, message: str, detail: Optional[dict] = None) -> TapResult:
        return TapResult(ok=ok, event=event, message=message,
                         phase=self.phase.value, detail=detail or {})

    # ---------- 狀態查詢 ----------
    def state(self) -> dict:
        return {
            "phase": self.phase.value,
            "turn": self._current_player().name if self.players else None,
            "current_monster": (
                {"name": self.current.name, "hp": self.current.hp, "atk": self.current.atk,
                 "reward": self.current.reward, "boss": self.current.boss}
                if self.current else None
            ),
            "slain": [{"monster": m, "killer": k} for m, k in self.slain],
            "winner": self.winner,
            "leaderboard": self.leaderboard(),
            "party": [
                {"name": p.name, "seat": p.seat, "hp": p.hero.hp, "max_hp": p.hero.max_hp,
                 "atk": p.hero.atk, "clazz": p.hero.clazz, "gold": p.gold, "kos": p.kos}
                for p in self.players
            ],
        }
