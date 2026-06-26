# S4 — Détection de régimes de marché (probabiliste + symbolique)

> Projet **Intelligence Symbolique** (SCIA / EPITA 2026) — sujet **S4**, difficulté 3/5.
> **Membres** : Samuel Krief et Nicolas Teisseire · **Dossier** : `S4-Programmation-probabiliste-symbolique-pour-la-detection-de-regimes-de-marche/`

## L'idée en bref

Un HMM détecte les régimes de marché (*bull* / *range* / *bear*) numériquement, mais ses labels « clignotent » et autorisent des transitions absurdes (bull → crash direct). On ajoute deux petites couches **symboliques** pour stabiliser le régime, puis on alloue un portefeuille selon le régime obtenu et on backtest contre le HMM seul et le buy-and-hold.

## Les 3 couches

1. **Probabiliste** (`src/hmm.py`) — HMM gaussien (`hmmlearn`) sur les rendements → régime + probabilité par date.
2. **Révision AGM** (`src/agm.py`) — on ne change de régime *cru* que si l'évidence est forte et persistante, au lieu de suivre l'argmax bruité du HMM.
3. **Qualitative** (`src/qualitative.py`) — on interdit les transitions illogiques (table des transitions autorisées) ; une transition interdite est corrigée.

→ régime final → **allocation simple** (`src/strategy.py`).

## La stratégie (volontairement simple)

Un seul actif risqué (ex : `SPY`) :

| Régime | Exposition |
|--------|-----------|
| bull   | 100 %     |
| range  | 50 %      |
| bear   | 0 % (cash)|

**Backtest local** (pandas) comparé à : (1) buy-and-hold, (2) HMM pur (même allocation sans les couches AGM/qualitative). On regarde rendement total, Sharpe, max drawdown.

> L'énoncé mentionne *QuantConnect Lean*. Ici on reste sur un backtest **local** pour faire simple ; QuantConnect pourra être branché plus tard si besoin.

## Structure

```
groupe-XX-s4-regimes-marche/
├── README.md
├── requirements.txt
├── s4_regimes.ipynb      # LE notebook = livrable complet (les 3 couches + backtest)
└── src/
    ├── hmm.py            # couche 1 — HMM
    ├── agm.py            # couche 2 — révision AGM
    ├── qualitative.py    # couche 3 — transitions cohérentes
    └── strategy.py       # régime → allocation + backtest
```

## Lancer

```bash
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
jupyter notebook s4_regimes.ipynb
```

## Ressources (cours CoursIA)

- `Probas/PyMC-HMM-Trading-Alpha.ipynb` — HMM appliqué au trading (point de départ couche 1).
- `Tweety-4-Belief-Revision.ipynb` — AGM (couche 2) — _à récupérer, absent des zips fournis_.
- `Python/QC-Py-Cloud-05-RegimeSwitching.ipynb` — allocation regime-switching (inspiration couche 4).

## Références

- Hamilton (1989), *A New Approach to the Economic Analysis of Nonstationary Time Series*.
- Alchourrón, Gärdenfors & Makinson (1985), *On the Logic of Theory Change* (AGM).
- Wellman (1990), *Fundamental Concepts of Qualitative Probabilistic Networks*.

## À faire

- [ ] Couche 1 — HMM (fit + proba de régime)
- [ ] Couche 2 — révision AGM minimale
- [ ] Couche 3 — table des transitions autorisées
- [ ] Stratégie + backtest local vs HMM pur vs buy-and-hold
- [ ] Notebook explicatif + slides
