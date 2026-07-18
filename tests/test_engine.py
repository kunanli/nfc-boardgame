"""最小單位測試：規則(rules)、目標(goal)、玩家(players) —— 競爭模式「搶尾刀奪寶」。

執行：  python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from game.cards import CardDB
from game.engine import Game, Phase


# 卡片 UID（對應 cards.json）
WARRIOR = "04A1B2C3"   # hp30 atk6
RANGER = "04A1B2C4"    # hp22 atk8
CLERIC = "04A1B2C5"    # hp24 atk4 heal5
MAGE = "04A1B2C6"      # hp18 atk10
GOBLIN = "04D0E0F1"    # hp12 atk3 reward5
WOLF = "04D0E0F2"      # hp20 atk5 reward8
GOLEM = "04D0E0F3"     # hp34 atk7 reward12
DRAGON = "04D0E0FF"    # hp60 atk12 boss reward30
POTION = "04C0FFEE1"   # heal10
RUNE = "04C0FFEE2"     # buff_atk3

UID_BY_NAME = {
    "戰士 · 阿爾": WARRIOR, "遊俠 · 琳": RANGER,
    "牧師 · 索恩": CLERIC, "法師 · 薇拉": MAGE,
}


def new_game() -> Game:
    return Game(CardDB.load())


def play_to_end(g: Game, monster_uid: str, max_taps: int = 200) -> Game:
    """翻出一隻怪，之後照輪替讓當前玩家自動出手，直到怪死或遊戲結束。"""
    g.tap(monster_uid)
    taps = 0
    while g.phase == Phase.ADVENTURE and g.current is not None and taps < max_taps:
        current = g.state()["turn"]
        g.tap(UID_BY_NAME[current])
        taps += 1
    return g


class TestPlayers(unittest.TestCase):
    """玩家：刷英雄卡組隊、各自計分。"""

    def test_join_party(self):
        g = new_game()
        r = g.tap(WARRIOR)
        self.assertTrue(r.ok)
        self.assertEqual(r.event, "player_joined")
        self.assertEqual(len(g.players), 1)

    def test_no_duplicate_hero(self):
        g = new_game()
        g.tap(WARRIOR)
        r = g.tap(WARRIOR)
        self.assertFalse(r.ok)
        self.assertEqual(r.event, "duplicate")

    def test_unknown_blank_card(self):
        g = new_game()
        r = g.tap("DEADBEEF")  # 未登錄的空白卡
        self.assertFalse(r.ok)
        self.assertEqual(r.event, "unknown_card")

    def test_non_member_cannot_attack(self):
        g = new_game()
        g.tap(WARRIOR)
        g.start_adventure()
        g.tap(GOBLIN)
        r = g.tap(RANGER)  # 遊俠沒加入
        self.assertFalse(r.ok)
        self.assertEqual(r.event, "not_in_party")


class TestRules(unittest.TestCase):
    """規則：翻怪、輪流出手、尾刀奪寶、反擊、撤退懲罰。"""

    def test_reveal_then_only_current_turn_can_act(self):
        g = new_game()
        g.tap(WARRIOR)  # seat0
        g.tap(RANGER)   # seat1
        g.start_adventure()
        rv = g.tap(GOBLIN)
        self.assertEqual(rv.event, "monster_revealed")
        r = g.tap(RANGER)  # 還沒輪到 seat1
        self.assertFalse(r.ok)
        self.assertEqual(r.event, "not_your_turn")

    def test_cannot_reveal_two_monsters(self):
        g = new_game()
        g.tap(WARRIOR)
        g.start_adventure()
        g.tap(GOBLIN)
        r = g.tap(WOLF)
        self.assertFalse(r.ok)
        self.assertEqual(r.event, "monster_present")

    def test_attack_without_monster(self):
        g = new_game()
        g.tap(WARRIOR)
        g.start_adventure()
        r = g.tap(WARRIOR)
        self.assertFalse(r.ok)
        self.assertEqual(r.event, "no_monster")

    def test_last_hit_takes_the_reward(self):
        # 戰士(atk6) 先手削血，法師(atk10) 補刀 -> 獎勵全歸法師
        g = new_game()
        g.tap(WARRIOR)  # seat0
        g.tap(MAGE)     # seat1
        g.start_adventure()
        g.tap(GOBLIN)          # hp12
        r1 = g.tap(WARRIOR)    # 12-6=6，未死，反擊戰士
        self.assertEqual(r1.event, "attack")
        r2 = g.tap(MAGE)       # 6-10 -> 補刀
        self.assertEqual(r2.event, "last_hit")
        self.assertEqual(g.players[1].gold, 5)  # 法師獨得
        self.assertEqual(g.players[0].gold, 0)  # 戰士只削血、沒拿到

    def test_counter_hits_the_attacker(self):
        g = new_game()
        g.tap(WARRIOR)  # hp30
        g.tap(MAGE)
        g.start_adventure()
        g.tap(GOBLIN)          # atk3
        g.tap(WARRIOR)         # 未殺死 -> 被反擊3
        self.assertEqual(g.players[0].hero.hp, 27)

    def test_knockout_revives_and_penalizes_gold(self):
        # 法師單挑：先靠補刀賺 5 金，再被巨龍打倒 -> 撤退回城、滿血、扣 3 金
        g = new_game()
        g.tap(MAGE)  # hp18 atk10
        g.start_adventure()
        play_to_end(g, GOBLIN)          # 補刀哥布林 +5
        self.assertEqual(g.players[0].gold, 5)
        g.tap(DRAGON)                   # 巨龍 atk12
        # 一路打到被 KO
        koed = False
        for _ in range(10):
            r = g.tap(MAGE)
            if r.detail.get("knocked_out"):
                koed = True
                break
        self.assertTrue(koed)
        p = g.players[0]
        self.assertEqual(p.hero.hp, p.hero.max_hp)  # 滿血復活
        self.assertEqual(p.gold, 2)                 # 5 - 3 懲罰
        self.assertEqual(p.kos, 1)


class TestItems(unittest.TestCase):
    """道具卡：消耗自己的回合使用。"""

    def test_rune_buffs_attack_and_uses_turn(self):
        g = new_game()
        g.tap(WARRIOR)  # seat0 atk6
        g.tap(RANGER)   # seat1
        g.start_adventure()
        r = g.tap(RUNE)  # 由當前玩家(戰士)使用
        self.assertTrue(r.ok)
        self.assertEqual(g.players[0].hero.atk, 9)      # 6+3
        self.assertEqual(g.state()["turn"], "遊俠 · 琳")  # 回合已交出

    def test_potion_heals_current_player(self):
        g = new_game()
        g.tap(WARRIOR)  # 單人，回合永遠是自己
        g.start_adventure()
        g.tap(WOLF)            # atk5，砍不死會被反擊
        g.tap(WARRIOR)
        g.tap(WARRIOR)
        injured_hp = g.players[0].hero.hp
        self.assertLess(injured_hp, 30)
        r = g.tap(POTION)
        self.assertTrue(r.ok)
        self.assertGreater(g.players[0].hero.hp, injured_hp)


class TestGoal(unittest.TestCase):
    """目標：打倒最終王時，金幣最多者獲勝。"""

    def test_boss_kill_ends_game_and_decides_winner(self):
        g = new_game()
        g.tap(WARRIOR)  # seat0 atk6
        g.tap(MAGE)     # seat1 atk10
        g.start_adventure()
        play_to_end(g, DRAGON)  # 一路輪替直到有人補掉巨龍
        self.assertEqual(g.phase, Phase.OVER)
        self.assertIsNotNone(g.winner)
        # 補掉 boss 的人獨得 30 金，應為金幣最高、即贏家
        board = g.leaderboard()
        self.assertEqual(board[0]["name"], g.winner)
        self.assertEqual(board[0]["gold"], 30)

    def test_no_play_after_game_over(self):
        g = new_game()
        g.tap(MAGE)
        g.start_adventure()
        play_to_end(g, DRAGON)
        self.assertEqual(g.phase, Phase.OVER)
        r = g.tap(GOBLIN)
        self.assertFalse(r.ok)
        self.assertEqual(r.event, "game_over")

    def test_higher_hoard_can_beat_the_boss_killer(self):
        # 競爭張力：補到 boss 不一定贏，看總金幣
        g = new_game()
        g.tap(WARRIOR)  # seat0
        g.tap(MAGE)     # seat1
        g.start_adventure()
        # 人為讓戰士囤積大量金幣
        g.players[0].gold = 100
        play_to_end(g, DRAGON)
        self.assertEqual(g.phase, Phase.OVER)
        self.assertEqual(g.winner, "戰士 · 阿爾")  # 囤金者贏，即使沒補到 boss


if __name__ == "__main__":
    unittest.main()
