import re

def remove_special_chars(v: str) -> str:
    return re.sub('[,%kmbt<>\b]', '', v, flags=re.IGNORECASE)


def replace_x_x(match):
    letter = match.group()[0].upper()
    return f"({letter}o{letter})"
