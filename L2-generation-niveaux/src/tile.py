from enum import IntEnum
from typing import Dict, FrozenSet


class TileType(IntEnum):
    VOID   = 0
    WALL   = 1
    FLOOR  = 2
    START  = 3
    END    = 4
    ENEMY  = 5
    ITEM   = 6
    TRAP   = 7


SYMBOLS: Dict[TileType, str] = {
    TileType.VOID:  "·",
    TileType.WALL:  "█",
    TileType.FLOOR: " ",
    TileType.START: "S",
    TileType.END:   "E",
    TileType.ENEMY: "X",
    TileType.ITEM:  "$",
    TileType.TRAP:  "^",
}

COLORS: Dict[TileType, str] = {
    TileType.VOID:  "\033[90m",
    TileType.WALL:  "\033[37m",
    TileType.FLOOR: "\033[0m",
    TileType.START: "\033[92m",
    TileType.END:   "\033[91m",
    TileType.ENEMY: "\033[31m",
    TileType.ITEM:  "\033[93m",
    TileType.TRAP:  "\033[35m",
}
RESET = "\033[0m"

WALKABLE: FrozenSet[TileType] = frozenset({
    TileType.FLOOR,
    TileType.START,
    TileType.END,
    TileType.ENEMY,
    TileType.ITEM,
    TileType.TRAP,
})

STRUCTURAL = [TileType.VOID, TileType.WALL, TileType.FLOOR]

WFC_RULES: Dict[TileType, Dict[int, FrozenSet[TileType]]] = {
    TileType.VOID: {
        d: frozenset({TileType.VOID, TileType.WALL})
        for d in range(4)
    },
    TileType.WALL: {
        d: frozenset({TileType.VOID, TileType.WALL, TileType.FLOOR})
        for d in range(4)
    },
    TileType.FLOOR: {
        d: frozenset({TileType.WALL, TileType.FLOOR})
        for d in range(4)
    },
}

WEIGHTS: Dict[TileType, float] = {
    TileType.VOID:  0.25,
    TileType.WALL:  2.0,
    TileType.FLOOR: 3.0,
}
