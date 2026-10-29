"""Deterministic packaging and unit conversion utilities."""

from typing import Optional, Tuple


def normalize_quantity_and_unit(
    qty: int,
    unit_str: Optional[str],
    pack_size: int = 1,
) -> Tuple[int, str]:
    """Convert package units (e.g. strips) to base units (tablets) deterministically.
    
    1 strip = pack_size tablets (default 10 for tablets).
    """
    safe_qty = max(0, int(qty))
    unit_norm = (unit_str or "").strip().lower()

    if unit_norm in ("strip", "strips"):
        multiplier = pack_size if pack_size > 1 else 10
        return (safe_qty * multiplier, "tablet")

    if unit_norm in ("tab", "tabs", "tablet", "tablets", "nos", "no"):
        return (safe_qty, "tablet")

    if unit_norm in ("vial", "vials"):
        return (safe_qty, "vial")

    if unit_norm in ("amp", "ampoule", "ampoules"):
        return (safe_qty, "ampoule")

    if unit_norm in ("bottle", "bottles", "bot"):
        return (safe_qty, "bottle")

    if unit_norm in ("sachet", "sachets", "pkt", "packet", "packets"):
        return (safe_qty, "sachet")

    return (safe_qty, unit_norm or "unit")
