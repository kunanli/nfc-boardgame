"""卡片資料庫：把 NFC UID 對應到卡片定義，並產生對應的領域物件。

真實硬體流程：讀卡機讀到晶片 UID -> 這裡查表 -> 得到卡片意義。
空白卡就是「還沒登錄 UID」的卡，登錄一筆資料即可賦予身分。
"""
from __future__ import annotations

import json
import os
from typing import Dict

from .models import Hero, Monster

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "cards.json")


class CardDB:
    def __init__(self, data: Dict[str, dict]):
        # data: uid -> 卡片定義
        self._cards = data

    @classmethod
    def load(cls, path: str = _DEFAULT_PATH) -> "CardDB":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return cls(raw["cards"])

    def has(self, uid: str) -> bool:
        return uid in self._cards

    def type_of(self, uid: str) -> str:
        """回傳卡片種類：hero / monster / item；未登錄的卡回傳 'unknown'。"""
        card = self._cards.get(uid)
        return card["type"] if card else "unknown"

    def raw(self, uid: str) -> dict:
        return self._cards[uid]

    def make_hero(self, uid: str) -> Hero:
        c = self._cards[uid]
        return Hero(
            uid=uid,
            name=c["name"],
            max_hp=c["hp"],
            atk=c["atk"],
            clazz=c.get("clazz", "adventurer"),
            heal=c.get("heal", 0),
        )

    def make_monster(self, uid: str) -> Monster:
        c = self._cards[uid]
        return Monster(
            uid=uid,
            name=c["name"],
            max_hp=c["hp"],
            atk=c["atk"],
            reward=c.get("reward", 0),
            boss=c.get("boss", False),
        )
