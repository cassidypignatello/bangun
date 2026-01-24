"""
Text normalization utilities for consistent material name matching.

Provides deterministic normalization to ensure cache hits even when
material names have slight variations (spacing, word order, units).
"""

import re


def normalize_material_name(name: str) -> str:
    """
    Normalize a material name for consistent cache lookups.

    Produces a canonical form that matches even with variations in:
    - Case (Semen Portland vs semen portland)
    - Spacing (50 kg vs 50kg)
    - Word order (Portland Semen vs Semen Portland)
    - Special characters (Semen - Portland vs Semen Portland)

    Args:
        name: Raw material name (e.g., "Semen Portland 50 kg")

    Returns:
        str: Normalized name (e.g., "50kg portland semen")

    Examples:
        >>> normalize_material_name("Semen Portland 50 kg")
        '50kg portland semen'
        >>> normalize_material_name("Portland Semen 50kg")
        '50kg portland semen'
        >>> normalize_material_name("Cat Tembok - Putih 5L")
        '5l cat putih tembok'
    """
    if not name:
        return ""

    # Step 1: Lowercase and strip
    text = name.lower().strip()

    # Step 2: Remove non-alphanumeric characters except spaces
    # Keep letters, numbers, and spaces only
    text = re.sub(r"[^a-z0-9\s]", "", text)

    # Step 3: Collapse multiple spaces to single space
    text = re.sub(r"\s+", " ", text).strip()

    # Step 4: Remove spaces before common units
    # Pattern: number followed by space then unit abbreviation
    # Handles: 50 kg -> 50kg, 10 m -> 10m, 5 l -> 5l, 100 cm -> 100cm
    unit_pattern = r"(\d+)\s+(kg|g|mg|l|ml|m|cm|mm|m2|m3|pcs|unit|set|roll|lembar|batang|sak|dus|box)"
    text = re.sub(unit_pattern, r"\1\2", text)

    # Step 5: Split into words and sort alphabetically
    words = text.split()
    words.sort()

    # Step 6: Join back together
    return " ".join(words)
