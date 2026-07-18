"""領域模型：卡片、英雄、怪物、玩家。

NFC 晶片本身只帶一個 UID，這裡的物件是「服務端」對那張卡的解讀。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Hero:
    """英雄卡：每位玩家持有一張，代表其在隊伍中的角色。"""
    uid: str
    name: str
    max_hp: int
    atk: int
    clazz: str = "adventurer"
    heal: int = 0          # 牧師類每回合可回復的隊友血量，0 表示不會治療
    hp: int = field(default=0)

    def __post_init__(self) -> None:
        if self.hp <= 0:
            self.hp = self.max_hp

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, dmg: int) -> None:
        self.hp = max(0, self.hp - dmg)

    def restore(self, amount: int) -> None:
        if self.alive:
            self.hp = min(self.max_hp, self.hp + amount)


@dataclass
class Monster:
    """怪物卡：boss=True 者為最終王，是遊戲的目標。"""
    uid: str
    name: str
    max_hp: int
    atk: int
    reward: int = 0
    boss: bool = False
    hp: int = field(default=0)

    def __post_init__(self) -> None:
        if self.hp <= 0:
            self.hp = self.max_hp

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def take_damage(self, dmg: int) -> None:
        self.hp = max(0, self.hp - dmg)


@dataclass
class Player:
    """玩家：由一張英雄卡代表，透過刷卡加入隊伍。

    競爭模式下每位玩家各自累積 gold（戰利品），尾刀者獨得怪物獎勵。
    """
    hero: Hero
    seat: Optional[int] = None
    gold: int = 0
    kos: int = 0   # 被打倒撤退的次數

    @property
    def name(self) -> str:
        return self.hero.name

    @property
    def alive(self) -> bool:
        return self.hero.alive
