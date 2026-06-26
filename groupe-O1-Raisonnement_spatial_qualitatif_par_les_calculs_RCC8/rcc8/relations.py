from enum import Enum

"""
règle RCC8 (composition)

Si :

A — R1 — B
B — R2 — C

Alors :

A — (R1 ∘ R2) — C

"""


class RCC8(str, Enum):
    """
    RCC8 (Region Connection Calculus) relations.
    Topological relations between spatial regions.
    """

    DC = "DC"      # Disconnected
    EC = "EC"      # Externally Connected
    PO = "PO"      # Partial Overlap
    EQ = "EQ"      # Equal
    TPP = "TPP"    # Tangential Proper Part
    NTPP = "NTPP"  # Non-Tangential Proper Part
    TPPI = "TPPI"  # Inverse of TPP
    NTPPI = "NTPPI"  # Inverse of NTPP


ALL_RELATIONS = frozenset(r.value for r in RCC8)

_SYMMETRIC_RELATIONS = frozenset({
    RCC8.DC.value,
    RCC8.EC.value,
    RCC8.PO.value,
    RCC8.EQ.value,
})

_INVERSE_RELATIONS = {
    RCC8.DC.value: RCC8.DC.value,
    RCC8.EC.value: RCC8.EC.value,
    RCC8.PO.value: RCC8.PO.value,
    RCC8.EQ.value: RCC8.EQ.value,
    RCC8.TPP.value: RCC8.TPPI.value,
    RCC8.TPPI.value: RCC8.TPP.value,
    RCC8.NTPP.value: RCC8.NTPPI.value,
    RCC8.NTPPI.value: RCC8.NTPP.value,
}


def relation_value(r: RCC8 | str) -> str:
    """
    Retourne la valeur canonique d'une relation RCC8.
    """
    value = r.value if isinstance(r, RCC8) else r

    if value not in ALL_RELATIONS:
        raise ValueError(f"Unknown RCC8 relation: {r!r}")

    return value


def is_symmetric(r: RCC8 | str) -> bool:
    """
    Check if a relation is symmetric.
    """
    return relation_value(r) in _SYMMETRIC_RELATIONS


# ----------------------------
# Helpers
# ----------------------------

def inverse_relation(r: RCC8 | str) -> RCC8 | str:
    """
    Retourne la relation inverse RCC8.

    Exemple:
        TPP  -> TPPI
        TPPI -> TPP
        EC   -> EC (symétrique)
    """
    inverse = _INVERSE_RELATIONS[relation_value(r)]
    return RCC8(inverse) if isinstance(r, RCC8) else inverse


def normalize_relations(relations) -> set[str]:
    """
    Normalise un ensemble de relations RCC8 en chaînes.
    """
    if isinstance(relations, (RCC8, str)):
        return {relation_value(relations)}

    return {relation_value(r) for r in relations}


def inverse_relations(relations) -> set[str]:
    """
    Retourne l'ensemble des relations inverses.
    """
    return {inverse_relation(relation_value(r)) for r in relations}
