"""Genetic-algorithm Sudoku solver.

Each chromosome row is a permutation of 1..9 respecting that row's clues, so row
constraints hold by construction; fitness counts only column and box duplicates.
Stops at a zero-conflict individual or when the generation budget runs out.

Stochastic: succeeds on easy/medium grids, struggles on hard ones. The benchmark
runs it over several seeds and reports a success rate.
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

from ..board import EMPTY, N, Grid
from .base import Solver

Chromosome = List[List[int]]  # 9 rows, each a permutation of 1..9


class GeneticSolver(Solver):
    name = "genetic"

    def __init__(
        self,
        population: int = 200,
        generations: int = 400,
        elite: int = 10,
        mutation_rate: float = 0.25,
        tournament: int = 5,
        restarts: int = 3,
        seed: Optional[int] = None,
    ):
        self.population = population
        self.generations = generations
        self.elite = elite
        self.mutation_rate = mutation_rate
        self.tournament = tournament
        self.restarts = restarts
        self.seed = seed

    def _solve(self, grid: Grid):
        rng = random.Random(self.seed)
        fixed = self._fixed_mask(grid)
        total_gens = 0
        best_fitness = None
        for _ in range(self.restarts):
            solution, gens, fit = self._evolve(grid, fixed, rng)
            total_gens += gens
            best_fitness = fit if best_fitness is None else min(best_fitness, fit)
            if solution is not None:
                return solution, total_gens, {
                    "generations": total_gens,
                    "best_fitness": 0,
                }
        return None, total_gens, {
            "generations": total_gens,
            "best_fitness": best_fitness,
        }

    # ---- GA internals ----------------------------------------------------
    def _fixed_mask(self, grid: Grid) -> List[List[Optional[int]]]:
        return [[grid.at(r, c) or None for c in range(N)] for r in range(N)]

    def _random_row(self, fixed_row: List[Optional[int]], rng: random.Random) -> List[int]:
        used = [v for v in fixed_row if v]
        missing = [v for v in range(1, 10) if v not in used]
        rng.shuffle(missing)
        row, it = [], iter(missing)
        for v in fixed_row:
            row.append(v if v else next(it))
        return row

    def _random_individual(self, fixed, rng) -> Chromosome:
        return [self._random_row(fixed[r], rng) for r in range(N)]

    @staticmethod
    def _fitness(ind: Chromosome) -> int:
        """Number of duplicate conflicts in columns and boxes (0 = solved)."""
        conflicts = 0
        for c in range(N):
            col = [ind[r][c] for r in range(N)]
            conflicts += N - len(set(col))
        for br in range(0, N, 3):
            for bc in range(0, N, 3):
                box = [ind[br + dr][bc + dc] for dr in range(3) for dc in range(3)]
                conflicts += N - len(set(box))
        return conflicts

    def _mutate(self, ind: Chromosome, fixed, rng: random.Random) -> None:
        for r in range(N):
            if rng.random() < self.mutation_rate:
                free = [c for c in range(N) if not fixed[r][c]]
                if len(free) >= 2:
                    a, b = rng.sample(free, 2)
                    ind[r][a], ind[r][b] = ind[r][b], ind[r][a]

    def _crossover(self, p1: Chromosome, p2: Chromosome, rng: random.Random) -> Chromosome:
        # Row-wise uniform crossover: each child row comes from one parent.
        return [list(p1[r]) if rng.random() < 0.5 else list(p2[r]) for r in range(N)]

    def _tournament_select(self, pop, fits, rng) -> Chromosome:
        best_idx = None
        for _ in range(self.tournament):
            i = rng.randrange(len(pop))
            if best_idx is None or fits[i] < fits[best_idx]:
                best_idx = i
        return pop[best_idx]

    def _evolve(self, grid, fixed, rng) -> Tuple[Optional[Grid], int, int]:
        pop = [self._random_individual(fixed, rng) for _ in range(self.population)]
        for gen in range(1, self.generations + 1):
            fits = [self._fitness(ind) for ind in pop]
            ranked = sorted(range(len(pop)), key=lambda i: fits[i])
            if fits[ranked[0]] == 0:
                return self._to_grid(pop[ranked[0]]), gen, 0
            new_pop = [pop[ranked[i]] for i in range(self.elite)]  # elitism
            while len(new_pop) < self.population:
                p1 = self._tournament_select(pop, fits, rng)
                p2 = self._tournament_select(pop, fits, rng)
                child = self._crossover(p1, p2, rng)
                self._mutate(child, fixed, rng)
                new_pop.append(child)
            pop = new_pop
        final_fits = [self._fitness(ind) for ind in pop]
        return None, self.generations, min(final_fits)

    @staticmethod
    def _to_grid(ind: Chromosome) -> Grid:
        return Grid(tuple(ind[r][c] for r in range(N) for c in range(N)))
