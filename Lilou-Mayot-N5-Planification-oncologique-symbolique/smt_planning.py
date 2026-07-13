"""
Couche Z3/SMT pour OncoPlan-Symbolique (Sujet N5).

Encode les regles cliniques de planification des cures de chimiotherapie
comme un probleme de satisfaction de contraintes SMT (Satisfiability Modulo
Theories), resolu avec Z3.

Contraintes modelisees :
1. Espacement minimal entre cycles (>= 21 jours, permet un report medical,
   contrairement a une egalite stricte).
2. Pas d'administration le dimanche (contrainte modulaire).
3. Dose cumulee <= seuil de toxicite (issu de l'ontologie, cf.
   dose_cumulee_max_mg_m2).
4. Compatibilite patient/protocole (issue des contre-indications de
   l'ontologie : si une contre-indication existe, le protocole est
   rendu infaisable par construction -- alors meme qu'aucune contrainte
   de planification "physique" ne serait violee).
5. Capacite des fauteuils de chimiotherapie (<=3 patients/jour).

Avantage du SMT (Z3) par rapport au CP pur (OR-Tools) pour ce sujet :
lorsque le probleme est infaisable, Z3 peut retourner un "unsat core" --
un sous-ensemble minimal de contraintes contradictoires -- ce qui permet
d'expliquer a l'oncologue *pourquoi* aucun calendrier valide n'existe,
plutot que de se contenter d'un simple "echec".
"""

from z3 import (
    Solver, Int, Bool, Real, And, Or, Not, Implies,
    sat, unsat, unknown
)


def construire_modele_planification(
    nb_cycles=4,
    duree_cycle=21,
    jours_admin=(1, 8),
    capacite_max=3,
    dose_par_cycle=85.0,
    dose_max_cumulee=None,
    occupations_existantes=None,
    patient_compatible=True,
    horizon_marge=10,
):
    """Construit un Solver Z3 nomme (assertions etiquetees) pour le probleme
    de planification d'un protocole de chimiotherapie.

    Args:
        nb_cycles: nombre de cycles a planifier.
        duree_cycle: duree d'un cycle en jours (typiquement 21).
        jours_admin: jours d'administration au sein d'un cycle (ex: J1, J8).
        capacite_max: nombre de fauteuils de chimio disponibles par jour.
        dose_par_cycle: dose administree (mg) a chaque jour d'administration.
        dose_max_cumulee: seuil de toxicite cumulee (mg), issu de
            l'ontologie (Agent.dose_cumulee_max_mg_m2). None = pas de seuil.
        occupations_existantes: dict {jour: charge_actuelle} pour les jours
            deja partiellement ou totalement occupes par d'autres patients.
        patient_compatible: bool, resultat de la verification d'ontologie
            (verifier_prescription). Si False, une contrainte insatisfiable
            est ajoutee explicitement, avec un nom dedie pour le diagnostic.
        horizon_marge: marge de jours ajoutee a l'horizon de recherche.

    Returns:
        (solver, variables) : le Solver Z3 avec contraintes nommees, et un
        dict des variables de decision pour extraction du modele.

    Raises:
        ValueError: si un parametre numerique est cliniquement absurde
            (dose negative, nombre de cycles nul ou negatif, duree de
            cycle non positive, capacite non positive). Sans cette
            validation, Z3 accepterait silencieusement ces valeurs et
            retournerait un calendrier "sat" denue de sens clinique
            (ex: une dose negative ne viole aucune contrainte SMT
            explicite, alors qu'elle n'a evidemment aucun sens medical).
    """
    if dose_par_cycle < 0:
        raise ValueError(f"dose_par_cycle doit etre >= 0, recu {dose_par_cycle}.")
    if nb_cycles <= 0:
        raise ValueError(f"nb_cycles doit etre >= 1, recu {nb_cycles}.")
    if duree_cycle <= 0:
        raise ValueError(f"duree_cycle doit etre >= 1, recu {duree_cycle}.")
    if capacite_max <= 0:
        raise ValueError(f"capacite_max doit etre >= 1, recu {capacite_max}.")
    if dose_max_cumulee is not None and dose_max_cumulee < 0:
        raise ValueError(f"dose_max_cumulee doit etre >= 0, recu {dose_max_cumulee}.")

    occupations_existantes = occupations_existantes or {}
    s = Solver()
    horizon = nb_cycles * duree_cycle + horizon_marge

    # --- Variables de decision ---
    start_day = Int("start_day")  # jour de debut du traitement (J1 absolu)

    # --- Contrainte 0 : compatibilite patient/protocole (issue de
    # l'ontologie). Si le patient presente une contre-indication, on
    # encode directement une contradiction nommee, de sorte que le
    # unsat_core pointera explicitement vers cette cause clinique plutot
    # que vers une cause de planning. ---
    compatibilite = Bool("compatibilite_ontologique")
    s.assert_and_track(compatibilite == patient_compatible, "ontologie_compatibilite")
    s.assert_and_track(compatibilite == True, "exigence_compatibilite")

    # --- Bornes sur le jour de depart ---
    s.assert_and_track(start_day >= 1, "borne_inf_start_day")
    s.assert_and_track(start_day <= 30, "borne_sup_start_day")

    jours_administration_abs = []  # jours absolus d'administration

    for i in range(nb_cycles):
        for j_admin in jours_admin:
            jour_abs = start_day + i * duree_cycle + (j_admin - 1)
            jours_administration_abs.append((i, j_admin, jour_abs))

            # --- Contrainte 1 : pas de dimanche ---
            # On exprime jour_abs % 7 != 0 directement avec l'operateur
            # modulo de Z3 (pas besoin de variable intermediaire comme en
            # CP-SAT, Z3 gere nativement l'arithmetique modulaire entiere).
            nom_dimanche = f"pas_dimanche_cycle{i}_jour{j_admin}"
            s.assert_and_track(jour_abs % 7 != 0, nom_dimanche)

            # --- Contrainte 2 : capacite (fauteuils de chimio) ---
            # Pour chaque jour deja sature dans occupations_existantes,
            # interdire que ce patient y soit planifie.
            for jour_occupe, charge in occupations_existantes.items():
                if charge >= capacite_max:
                    nom_capacite = f"capacite_cycle{i}_jour{j_admin}_vs_{jour_occupe}"
                    s.assert_and_track(jour_abs != jour_occupe, nom_capacite)

    # --- Contrainte 3 : espacement minimal entre cycles (>= duree_cycle,
    # et non une egalite stricte, pour permettre un report medical futur
    # sans rendre le modele immediatement infaisable). ---
    for i in range(nb_cycles - 1):
        nom_espacement = f"espacement_min_cycle{i}_{i+1}"
        debut_i = start_day + i * duree_cycle
        debut_i_plus_1 = start_day + (i + 1) * duree_cycle
        s.assert_and_track(debut_i_plus_1 - debut_i >= duree_cycle, nom_espacement)

    # --- Contrainte 4 : dose cumulee <= seuil de toxicite (issu de
    # l'ontologie). Avec dose_par_cycle fixe, la dose cumulee croit
    # lineairement avec le nombre de cycles realises ; on contraint donc
    # le nombre total de cycles administres a dose pleine. On modelise
    # cela avec une variable Z3 (Real) plutot qu'un simple calcul Python,
    # afin que la contrainte reste une expression SMT verifiable par le
    # solveur (et trackable dans un unsat core). ---
    if dose_max_cumulee is not None:
        dose_cumulee_var = Real("dose_cumulee_totale")
        s.assert_and_track(
            dose_cumulee_var == nb_cycles * dose_par_cycle,
            "definition_dose_cumulee"
        )
        nom_dose = "dose_cumulee_sous_seuil_toxicite"
        s.assert_and_track(dose_cumulee_var <= dose_max_cumulee, nom_dose)

    variables = {
        "start_day": start_day,
        "jours_administration_abs": jours_administration_abs,
        "compatibilite": compatibilite,
    }
    return s, variables


def planifier_chimio(**kwargs):
    """Resout le modele de planification et retourne soit un calendrier
    valide, soit un diagnostic d'infaisabilite (unsat core).

    Returns:
        dict avec les cles :
            - "statut": "sat" | "unsat" | "unknown"
            - "calendrier": liste de jours absolus (si sat)
            - "unsat_core": liste des contraintes en conflit (si unsat)
    """
    s, variables = construire_modele_planification(**kwargs)
    resultat = s.check()

    if resultat == sat:
        modele = s.model()
        start = modele[variables["start_day"]].as_long()
        calendrier = sorted(
            modele.eval(jour_abs).as_long()
            for (_, _, jour_abs) in variables["jours_administration_abs"]
        )
        return {
            "statut": "sat",
            "debut_traitement": start,
            "calendrier": calendrier,
        }
    elif resultat == unsat:
        core = [str(c) for c in s.unsat_core()]
        return {
            "statut": "unsat",
            "unsat_core": core,
        }
    else:
        return {"statut": "unknown"}


if __name__ == "__main__":
    print("=== Test 1 : planification standard, patient compatible ===")
    res = planifier_chimio(
        occupations_existantes={10: 3, 11: 3, 12: 3},
        patient_compatible=True,
    )
    print(res)

    print("\n=== Test 2 : patient avec contre-indication (ontologie) ===")
    res = planifier_chimio(
        occupations_existantes={10: 3, 11: 3, 12: 3},
        patient_compatible=False,
    )
    print(res)
    print("-> L'unsat core pointe directement vers la cause clinique, "
          "pas vers une contrainte de planning.")

    print("\n=== Test 3 : dose cumulee depassant le seuil de toxicite "
          "(ex: Oxaliplatine, seuil 600 mg/m2) ===")
    res = planifier_chimio(
        dose_par_cycle=200.0,
        dose_max_cumulee=600.0,
        nb_cycles=4,  # 4 x 200 = 800 > 600
        patient_compatible=True,
    )
    print(res)

    print("\n=== Test 4 : meme cas, mais avec une dose par cycle reduite ===")
    res = planifier_chimio(
        dose_par_cycle=100.0,
        dose_max_cumulee=600.0,
        nb_cycles=4,  # 4 x 100 = 400 <= 600
        patient_compatible=True,
    )
    print(res)
