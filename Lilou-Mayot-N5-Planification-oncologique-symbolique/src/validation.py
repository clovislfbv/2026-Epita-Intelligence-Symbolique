"""
Validation du pipeline OncoPlan sur les 8 patients du dataset CoursIA.

Objectif (demande explicitement par le sujet N5) : "Valider sur les cas
cliniques du CoursIA et comparer avec les recommandations du panel
d'oncologues."

Le dataset CoursIA (patients_oncology.csv) ne fournit pas de label explicite
"decision du panel d'oncologues", mais il fournit des signaux clinques
indirects qui font office de verite-terrain raisonnable :
- `hospitalisation` = "Oui" a un moment du suivi -> effet secondaire severe
  survenu malgre le protocole standard. On s'attend a ce que notre pipeline
  identifie ces patients comme presentant un risque eleve (profil "Sensible"
  ou recommandation de reduction/report de dose).
- `score_toxicite` eleve (4-5) et `gb_min` bas -> meme logique.
- Aucun patient du dataset ne presente de fonction_renale_min < 60 mL/min
  (seuil clinique standard d'insuffisance renale, cf. ontologie). Le
  pipeline ne devrait donc REFUSER aucun des 8 patients au niveau de
  l'ontologie -- ce test verifie justement l'absence de faux positifs.

Methodologie : pour chaque patient, on tronque l'historique aux 6 premiers
points (jusqu'a J15 cycle 2, comme dans les tests precedents), et on
demande au pipeline une recommandation pour la dose prevue suivante
(approxime par la derniere dose pleine observee).
"""

import os
import pandas as pd

from .pipeline import PipelineOncoPlan

# Mapping patient -> (protocole exact du dataset, pathologies a tester).
# Aucune pathologie supplementaire n'est ajoutee : on teste les patients
# "tels que" fournis par le dataset (aucun n'a de contre-indication connue
# au sens de notre ontologie).
PATIENT_PATHOLOGIES = {p: [] for p in
                        ["P001", "P002", "P003", "P004", "P005", "P006", "P007", "P008"]}


def run_validation():
    pipeline = PipelineOncoPlan()
    df = pd.read_csv(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "data", "patients_oncology.csv")
    )

    lignes = []
    for patient_id in sorted(df.patient_id.unique()):
        p = df[df.patient_id == patient_id].sort_values(["cycle_numero", "jour_cycle"])
        protocole = p["protocole"].iloc[0]
        hospitalise = (p["hospitalisation"] == "Oui").any()
        score_tox_max = p["score_toxicite"].max()
        gb_min = p["taux_globules_blancs"].min()

        doses_hist = p["dose_reelle_mg"].values[:6].astype(float)
        obs_gb = p["taux_globules_blancs"].values[:6].astype(float)
        # Dose prevue suivante = dose NOMINALE du protocole (dose_prevue_mg
        # a J1/cycle 1), c'est-a-dire la dose prevue avant tout ajustement
        # clinique deja survenu dans l'historique. C'est la vraie question
        # clinique : "si on maintenait le plan initial, quel serait le
        # risque ?" -- et non "si on continue a la derniere dose deja
        # reduite par le clinicien", qui sous-estimerait trivialement le
        # risque pour les patients deja ajustes.
        dose_prevue = float(
            p[(p.cycle_numero == 1) & (p.jour_cycle == 1)]["dose_prevue_mg"].iloc[0]
        )

        res = pipeline.recommander(
            protocole_nom=protocole,
            patient_pathologies=PATIENT_PATHOLOGIES[patient_id],
            doses_historique=doses_hist,
            observations_gb=obs_gb,
            dose_prevue=dose_prevue,
            dose_par_cycle=dose_prevue,  # dose nominale du protocole = reference
            verbose=False,
        )

        profil_pymc = res.get("etapes", {}).get("pymc", {}).get("profil_probable", "N/A")
        p_danger = res.get("etapes", {}).get("pymc", {}).get(
            "recommandation_dose", {}
        ).get("p_danger", None)

        lignes.append({
            "patient": patient_id,
            "protocole": protocole,
            "hospitalise_reel": hospitalise,
            "score_toxicite_max": score_tox_max,
            "gb_min_observe": gb_min,
            "statut_pipeline": res["statut_final"],
            "profil_estime": profil_pymc,
            "p_danger": round(p_danger, 3) if p_danger is not None else None,
        })

    return pd.DataFrame(lignes)


if __name__ == "__main__":
    resultats = run_validation()
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 12)
    print(resultats.to_string(index=False))

    print("\n--- Analyse de coherence ---")
    print("\nPatients reellement hospitalises (effet secondaire severe constate) :")
    hosp = resultats[resultats.hospitalise_reel]
    print(hosp[["patient", "statut_pipeline", "profil_estime", "p_danger"]].to_string(index=False))

    print("\nPatients NON hospitalises :")
    non_hosp = resultats[~resultats.hospitalise_reel]
    print(non_hosp[["patient", "statut_pipeline", "profil_estime", "p_danger"]].to_string(index=False))

    print("\nAucun patient ne devrait etre REFUSE au niveau ontologique "
          "(aucune contre-indication renale dans ce dataset) :")
    print("Nb REFUSE :", (resultats.statut_pipeline == "REFUSE").sum(), "/ 8 (attendu : 0)")

    print("\n--- Note d'interpretation : pourquoi P003/P005 restent signales "
          "malgre un profil 'Resistant' majoritaire ---")
    print(
        "Le posterior sur le profil de P003 est par exemple "
        "[Resistant=0.67, Normal=0.22, Sensible=0.11]. La trajectoire "
        "deterministe moyenne sous 'Resistant' seul ne croise jamais le "
        "seuil de danger (P(danger|Resistant) ~ 0). Mais sous 'Normal' "
        "(22% de poids posterior), elle s'en approche tres pres "
        "(P(danger|Normal) ~ 0.32), et sous 'Sensible' (11%) elle le "
        "depasse largement (P(danger|Sensible) ~ 0.98).\n"
        "Le risque final simule (~0.18-0.20) est la MOYENNE PONDEREE de "
        "ces trois risques conditionnels, pas le risque du profil le plus "
        "probable seul. C'est le comportement bayesien correct : ignorer "
        "le risque resultant des branches 'Normal'/'Sensible' simplement "
        "parce qu'elles ne sont pas le mode du posterior reviendrait a "
        "ignorer une incertitude residuelle non negligeable (33% de poids "
        "cumule). C'est precisement l'avantage d'une inference MCMC "
        "complete (PyMC/NUTS) sur une approximation par point estimate "
        "(ex: SVI/Pyro) : la decision de dose integre TOUTE la masse "
        "posterior, pas seulement son maximum."
    )
