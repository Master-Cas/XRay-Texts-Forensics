"""Within-prefix permutation test for context-keyed forced-choice association."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from .models import BlackBoxAnalysisResult, BlackBoxObservation, PrefixStatistic


def analyze_observations(
    observations: list[BlackBoxObservation],
    *,
    permutations: int = 999,
    seed: int = 0,
) -> BlackBoxAnalysisResult:
    if permutations < 1:
        raise ValueError("permutations must be >= 1")
    if not observations:
        raise ValueError("at least one observation is required")

    experiment_ids = {row.experiment_id for row in observations}
    if len(experiment_ids) != 1:
        raise ValueError("all observations must belong to one experiment")

    valid = [row for row in observations if row.valid and row.choice is not None]
    invalid_count = len(observations) - len(valid)
    if not valid:
        raise ValueError("no valid observations are available")

    choice_sets = {tuple(row.allowed_choices) for row in observations}
    if len(choice_sets) != 1:
        raise ValueError("all observations must use the same ordered choice set")
    choices = list(next(iter(choice_sets)))
    choice_index = {choice: index for index, choice in enumerate(choices)}

    prefix_ids = sorted({row.prefix_id for row in valid})
    context_ids = sorted({row.context_id for row in valid})
    context_index = {context: index for index, context in enumerate(context_ids)}

    groups: dict[str, list[BlackBoxObservation]] = defaultdict(list)
    for row in valid:
        groups[row.prefix_id].append(row)

    observed_stat, per_prefix = _statistic(
        groups,
        context_index=context_index,
        choice_index=choice_index,
    )

    rng = np.random.default_rng(seed)
    greater_equal = 0
    for _ in range(permutations):
        permuted: dict[str, list[BlackBoxObservation]] = {}
        for prefix_id, rows in groups.items():
            labels = [row.context_id for row in rows]
            rng.shuffle(labels)
            permuted[prefix_id] = [
                row.model_copy(update={"context_id": context_id})
                for row, context_id in zip(rows, labels, strict=True)
            ]
        perm_stat, _ = _statistic(
            permuted,
            context_index=context_index,
            choice_index=choice_index,
        )
        if perm_stat >= observed_stat - 1e-12:
            greater_equal += 1

    p_value = (greater_equal + 1) / (permutations + 1)
    return BlackBoxAnalysisResult(
        experiment_id=next(iter(experiment_ids)),
        valid_observations=len(valid),
        invalid_observations=invalid_count,
        prefix_count=len(prefix_ids),
        context_count=len(context_ids),
        choice_count=len(choices),
        statistic=observed_stat,
        association_index=observed_stat / len(valid),
        p_value=p_value,
        permutations=permutations,
        seed=seed,
        per_prefix=per_prefix,
    )


def _statistic(
    groups: dict[str, list[BlackBoxObservation]],
    *,
    context_index: dict[str, int],
    choice_index: dict[str, int],
) -> tuple[float, list[PrefixStatistic]]:
    total_stat = 0.0
    per_prefix: list[PrefixStatistic] = []

    for prefix_id in sorted(groups):
        rows = groups[prefix_id]
        table = np.zeros((len(context_index), len(choice_index)), dtype=float)
        for row in rows:
            if row.choice is None:
                continue
            table[context_index[row.context_id], choice_index[row.choice]] += 1.0

        statistic = _pearson_statistic(table)
        total_stat += statistic
        per_prefix.append(
            PrefixStatistic(
                prefix_id=prefix_id,
                statistic=statistic,
                valid_observations=len(rows),
                context_count=int(np.sum(table.sum(axis=1) > 0)),
                choice_count=int(np.sum(table.sum(axis=0) > 0)),
            )
        )

    return total_stat, per_prefix


def _pearson_statistic(table: np.ndarray) -> float:
    total = float(table.sum())
    if total <= 0:
        return 0.0
    row_sum = table.sum(axis=1, keepdims=True)
    col_sum = table.sum(axis=0, keepdims=True)
    expected = row_sum @ col_sum / total
    mask = expected > 0
    return float(np.sum(((table - expected) ** 2)[mask] / expected[mask]))
