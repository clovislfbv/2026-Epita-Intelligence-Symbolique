"""
Tests de validation du raisonneur RCC8.

Ce fichier peut etre execute directement avec:

    python3 -m rcc8.test

Les tests couvrent trois niveaux:
- les proprietes de base des relations RCC8;
- la forme et la coherence de la table de composition;
- le comportement du solveur PC-2 sur des reseaux coherents ou incoherents.
"""

from rcc8.composition_table import COMPOSE
from rcc8.rcc8solver import RCC8Solver
from rcc8.relations import ALL_RELATIONS, RCC8, inverse_relation, inverse_relations


def assert_relations(actual, expected, label="relations"):
    """
    Compare deux ensembles de relations avec un message d'erreur lisible.
    """
    assert actual == expected, (
        f"{label}: expected {sorted(expected)}, got {sorted(actual)}"
    )


def build_solver(vars=("A", "B", "C", "D")):
    """
    Construit un reseau RCC8 complet et non contraint.

    Au depart, chaque paire de regions peut avoir n'importe quelle relation
    RCC8. Les tests ajoutent ensuite des contraintes en remplacant certains
    ensembles par des singletons comme {"TPP"} ou {"EC"}.
    """
    R = {}

    for i in vars:
        for j in vars:
            if i == j:
                continue
            R[(i, j)] = set(ALL_RELATIONS)

    return RCC8Solver(list(vars), R)


def snapshot(solver):
    """
    Copie l'etat courant du reseau pour verifier la stabilite du solveur.
    """
    return {pair: set(relations) for pair, relations in solver.R.items()}


def assert_inconsistent(solver):
    """
    Verifie qu'un reseau est detecte comme incoherent par la propagation.
    """
    try:
        solver.pc2()
        assert False, "Inconsistency not detected"
    except ValueError:
        pass


def assert_converse_closed(solver):
    """
    Verifie que chaque contrainte possede son inverse correct.

    Pour tout couple (A, B), le domaine R(B,A) doit etre exactement l'inverse
    de R(A,B). C'est un invariant central pour un reseau RCC8.
    """
    for i in solver.vars:
        for j in solver.vars:
            if i == j:
                continue
            assert_relations(
                solver.R[(j, i)],
                inverse_relations(solver.R[(i, j)]),
                f"converse closure for {i}-{j}",
            )


def test_inverse_relation():
    """
    Verifie les inverses RCC8.

    Les relations DC, EC, PO et EQ sont symetriques. TPP/NTPP ne le sont pas:
    leur inverse doit etre TPPI/NTPPI.
    """
    assert inverse_relation("TPP") == "TPPI"
    assert inverse_relation("TPPI") == "TPP"
    assert inverse_relation("NTPP") == "NTPPI"
    assert inverse_relation("NTPPI") == "NTPP"
    assert inverse_relation("EC") == "EC"
    assert inverse_relation(RCC8.TPP) == RCC8.TPPI

    print("TEST INVERSE OK")


def test_inverse_relation_is_involution():
    """
    Verifie que l'inverse de l'inverse revient a la relation initiale.
    """
    for relation in ALL_RELATIONS:
        assert inverse_relation(inverse_relation(relation)) == relation

    print("TEST INVERSE INVOLUTION OK")


def test_composition_table_shape():
    """
    Verifie que la table de composition est complete et fermee.

    Complete: chaque relation composee avec chaque relation a une entree.
    Fermee: le resultat contient uniquement des relations RCC8 valides.
    """
    for r in ALL_RELATIONS:
        assert set(COMPOSE[r]) == set(ALL_RELATIONS)
        for s in ALL_RELATIONS:
            assert COMPOSE[r][s]
            assert COMPOSE[r][s] <= set(ALL_RELATIONS)

    print("TEST TABLE COMPLETE OK")


def test_composition_table_identity():
    """
    Verifie que EQ agit comme identite pour la composition.

    R o EQ = R et EQ o R = R.
    """
    for relation in ALL_RELATIONS:
        assert_relations(COMPOSE[relation]["EQ"], {relation}, f"{relation} o EQ")
        assert_relations(COMPOSE["EQ"][relation], {relation}, f"EQ o {relation}")

    print("TEST TABLE IDENTITY OK")


def test_composition_table_converse_coherence():
    """
    Verifie une propriete algebrique importante de RCC8.

    Pour deux relations R et S:

        inverse(R o S) = inverse(S) o inverse(R)

    Ce test attrape les erreurs de table qui cassent la coherence entre
    R(A,B) et R(B,A).
    """
    for r in ALL_RELATIONS:
        for s in ALL_RELATIONS:
            left = inverse_relations(COMPOSE[r][s])
            right = COMPOSE[inverse_relation(s)][inverse_relation(r)]
            assert left == right, f"Converse mismatch for {r} o {s}"

    print("TEST TABLE INVERSE OK")


def test_composition_table_known_cases():
    """
    Verifie quelques compositions RCC8 classiques.
    """
    known_cases = [
        ("TPP", "TPP", {"TPP", "NTPP"}),
        ("NTPP", "NTPP", {"NTPP"}),
        ("TPP", "NTPP", {"NTPP"}),
        ("NTPP", "TPP", {"NTPP"}),
        ("EC", "NTPP", {"PO", "TPP", "NTPP"}),
        ("DC", "TPPI", {"DC"}),
    ]

    for left, right, expected in known_cases:
        assert_relations(COMPOSE[left][right], expected, f"{left} o {right}")

    print("TEST TABLE KNOWN CASES OK")


def test_converse_propagation_with_two_variables():
    """
    Verifie que le solveur synchronise automatiquement la relation inverse.

    Si A est une partie propre tangentielle de B, alors B doit etre l'inverse
    de cette relation par rapport a A.
    """
    solver = build_solver(("A", "B"))

    solver.R[("A", "B")] = {"TPP"}
    solver.pc2()

    assert_relations(solver.R[("A", "B")], {"TPP"}, "A-B")
    assert_relations(solver.R[("B", "A")], {"TPPI"}, "B-A")
    assert_converse_closed(solver)

    print("TEST CONVERSE TWO VARIABLES OK")


def test_all_single_relation_converses():
    """
    Verifie tous les singletons de relation sur un reseau a deux regions.
    """
    for relation in ALL_RELATIONS:
        solver = build_solver(("A", "B"))

        solver.R[("A", "B")] = {relation}
        solver.pc2()

        assert_relations(solver.R[("A", "B")], {relation}, f"A-B {relation}")
        assert_relations(
            solver.R[("B", "A")],
            {inverse_relation(relation)},
            f"B-A inverse {relation}",
        )

    print("TEST ALL SINGLE CONVERSES OK")


def test_add_constraint_updates_converse():
    """
    Verifie l'API conseillee pour ajouter des contraintes.
    """
    solver = build_solver(("A", "B"))

    solver.add_constraint("A", "B", {"NTPP"})

    assert_relations(solver.R[("A", "B")], {"NTPP"}, "A-B")
    assert_relations(solver.R[("B", "A")], {"NTPPI"}, "B-A")

    print("TEST ADD CONSTRAINT CONVERSE OK")


def test_add_constraint_accepts_string_or_enum():
    """
    Verifie que l'API accepte une chaine ou une valeur RCC8.
    """
    solver = build_solver(("A", "B", "C"))

    solver.add_constraint("A", "B", "TPP")
    solver.add_constraint("B", "C", {RCC8.EC})
    solver.pc2()

    assert_relations(solver.R[("A", "B")], {"TPP"}, "A-B")
    assert_relations(solver.R[("B", "C")], {"EC"}, "B-C")
    assert_relations(solver.R[("A", "C")], {"DC", "EC"}, "A-C")
    assert_converse_closed(solver)

    print("TEST ADD CONSTRAINT TYPES OK")


def test_add_constraint_rejects_invalid_inputs():
    """
    Verifie que les entrees invalides echouent explicitement.
    """
    invalid_cases = [
        ("A", "B", "INVALID"),
        ("A", "Z", "TPP"),
        ("A", "A", "EQ"),
    ]

    for i, j, relation in invalid_cases:
        solver = build_solver(("A", "B"))
        try:
            solver.add_constraint(i, j, relation)
            assert False, f"Invalid constraint accepted: {(i, j, relation)}"
        except ValueError:
            pass

    print("TEST ADD CONSTRAINT INVALID INPUTS OK")


def test_symmetry():
    """
    Verifie qu'une relation symetrique reste identique dans les deux sens.
    """
    solver = build_solver(("A", "B"))

    solver.R[("A", "B")] = {"EC"}
    solver.pc2()

    assert_relations(solver.R[("A", "B")], {"EC"}, "A-B")
    assert_relations(solver.R[("B", "A")], {"EC"}, "B-A")
    assert_converse_closed(solver)

    print("TEST SYMETRIE OK")


def test_simple_coherent():
    """
    Teste une propagation simple sur trois regions.

    A TPP B signifie que A est dans B en touchant son bord.
    B EC C signifie que B touche C par le bord.
    Alors A et C ne peuvent etre que DC ou EC.
    """
    solver = build_solver(("A", "B", "C"))

    solver.add_constraint("A", "B", {"TPP"})
    solver.add_constraint("B", "C", {"EC"})
    solver.pc2()

    assert_relations(solver.R[("A", "C")], {"DC", "EC"}, "A-C")
    assert_relations(solver.R[("C", "A")], {"DC", "EC"}, "C-A")
    assert_converse_closed(solver)

    print("TEST SIMPLE OK")


def test_incoherent_direct():
    """
    Teste une contradiction visible apres composition.

    A TPP B et B TPP C impliquent que A est dans C. Imposer A DC C est donc
    impossible.
    """
    solver = build_solver(("A", "B", "C"))

    solver.add_constraint("A", "B", {"TPP"})
    solver.add_constraint("B", "C", {"TPP"})
    solver.add_constraint("A", "C", {"DC"})

    assert_inconsistent(solver)

    print("TEST INCOHERENCE DIRECT OK")


def test_chain_propagation():
    """
    Verifie une deduction classique par chaine.

    Si A est dans B et B est dans C, alors A est dans C. La relation finale
    peut etre TPP ou NTPP selon le contact avec le bord de C.
    """
    solver = build_solver(("A", "B", "C"))

    solver.add_constraint("A", "B", {"TPP"})
    solver.add_constraint("B", "C", {"TPP"})
    solver.pc2()

    assert_relations(solver.R[("A", "C")], {"TPP", "NTPP"}, "A-C")
    assert_relations(solver.R[("C", "A")], {"TPPI", "NTPPI"}, "C-A")
    assert_converse_closed(solver)

    print("TEST CHAINE OK")


def test_hidden_inconsistency():
    """
    Teste une contradiction indirecte.

    A NTPP B et B NTPP C impliquent que A est strictement a l'interieur de C.
    La contrainte inverse C DC A rend donc le reseau incoherent.
    """
    solver = build_solver(("A", "B", "C"))

    solver.add_constraint("A", "B", {"NTPP"})
    solver.add_constraint("B", "C", {"NTPP"})
    solver.add_constraint("C", "A", {"DC"})

    assert_inconsistent(solver)

    print("TEST HIDDEN INCONSISTENCY OK")


def test_complex_network():
    """
    Lance le solveur sur un petit reseau plus dense.

    Ici on ne cherche pas un resultat exact pour chaque paire: ce test sert a
    verifier que la propagation atteint un point fixe sans vider un domaine.
    """
    solver = build_solver(("A", "B", "C", "D"))

    solver.add_constraint("A", "B", {"TPP"})
    solver.add_constraint("B", "C", {"EC"})
    solver.add_constraint("C", "D", {"PO"})
    solver.add_constraint("A", "D", {
        "DC", "EC", "PO", "TPP", "NTPP", "TPPI", "NTPPI"
    })

    solver.pc2()

    for rels in solver.R.values():
        assert rels

    assert_converse_closed(solver)

    print("TEST COMPLEXE OK")


def test_solver_is_idempotent():
    """
    Verifie que relancer PC-2 apres convergence ne change plus le reseau.
    """
    solver = build_solver(("A", "B", "C", "D"))

    solver.add_constraint("A", "B", {"TPP"})
    solver.add_constraint("B", "C", {"TPP"})
    solver.add_constraint("C", "D", {"EC", "PO"})
    solver.pc2()

    first_result = snapshot(solver)
    solver.pc2()

    assert snapshot(solver) == first_result
    assert_converse_closed(solver)

    print("TEST IDEMPOTENCE OK")


def test_singleton_compositions_are_respected_by_solver():
    """
    Verifie que le solveur respecte la table pour toutes les compositions.

    Pour chaque couple R(A,B), R(B,C), la relation finale R(A,C) doit rester
    incluse dans la composition RCC8 R(A,B) o R(B,C).
    """
    for left in ALL_RELATIONS:
        for right in ALL_RELATIONS:
            solver = build_solver(("A", "B", "C"))

            solver.add_constraint("A", "B", {left})
            solver.add_constraint("B", "C", {right})
            solver.pc2()

            assert solver.R[("A", "C")] <= COMPOSE[left][right], (
                f"A-C is not compatible with {left} o {right}: "
                f"{sorted(solver.R[('A', 'C')])}"
            )
            assert_converse_closed(solver)

    print("TEST SOLVER COMPOSITIONS OK")


def test_manual_invalid_relation_is_rejected():
    """
    Verifie qu'une relation inconnue injectee dans le reseau est refusee.

    Ce test protege contre les fautes de frappe silencieuses comme "TPPi"
    au lieu de "TPPI".
    """
    solver = build_solver(("A", "B"))
    solver.R[("A", "B")] = {"TPPi"}

    try:
        solver.pc2()
        assert False, "Invalid relation was accepted"
    except ValueError:
        pass

    print("TEST MANUAL INVALID RELATION OK")


def run_all():
    """
    Execute tous les tests dans un ordre pedagogique.
    """
    test_inverse_relation()
    test_inverse_relation_is_involution()
    test_composition_table_shape()
    test_composition_table_identity()
    test_composition_table_converse_coherence()
    test_composition_table_known_cases()
    test_converse_propagation_with_two_variables()
    test_all_single_relation_converses()
    test_add_constraint_updates_converse()
    test_add_constraint_accepts_string_or_enum()
    test_add_constraint_rejects_invalid_inputs()
    test_symmetry()
    test_simple_coherent()
    test_incoherent_direct()
    test_chain_propagation()
    test_hidden_inconsistency()
    test_complex_network()
    test_solver_is_idempotent()
    test_singleton_compositions_are_respected_by_solver()
    test_manual_invalid_relation_is_rejected()


if __name__ == "__main__":
    run_all()
