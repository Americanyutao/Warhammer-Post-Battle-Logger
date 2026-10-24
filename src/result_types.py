"""Native per-alliance result types, shared with any future collector adapter."""
TYPES = {
    0: ('close_victory', 'Victory', 'Close Victory'),
    1: ('decisive_victory', 'Victory', 'Decisive Victory'),
    2: ('heroic_victory', 'Victory', 'Heroic Victory'),
    3: ('pyrrhic_victory', 'Victory', 'Pyrrhic Victory'),
    4: ('draw', 'Draw', 'Draw'),
    5: ('close_defeat', 'Defeat', 'Close Defeat'),
    6: ('decisive_defeat', 'Defeat', 'Decisive Defeat'),
    7: ('crushing_defeat', 'Defeat', 'Crushing Defeat'),
    8: ('valiant_defeat', 'Defeat', 'Valiant Defeat'),
}


def confirmed_label(code, key, outcome):
    item = TYPES.get(code)
    return item[2] if item and item[:2] == (key, outcome) else None
