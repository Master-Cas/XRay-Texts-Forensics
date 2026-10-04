"""Within-prefix permutation test for repeatable context-conditioned choice effects."""

from __future__ import annotations

import numpy as np

from .models import (
    BlackBoxDesign,
    BlackBoxResult,
    BlackBoxSelfTestReport,
    CellObservation,
)
from .providers import ChoiceProvider, SyntheticChoiceProvider


class BlackBoxExperiment:
    """Run a frozen forced-choice design and test context alignment across prefixes."""

    def __init__(self, design: BlackBoxDesign) -> None:
        self.design = design

    def collect(self, provider: ChoiceProvider) -> list[CellObservation]:
        observations: list[CellObservation] = []
        candidate_index = {
            candidate: index for index, candidate in enumerate(self.design.candidates)
        }

        for prefix_index, prefix in enumerate(self.design.prefixes):
            for context_index, context in enumerate(self.design.contexts):
                for sample_index in range(self.design.samples_per_cell):
                    choice = provider.choose(
                        prefix=prefix,
                        context=context,
                        candidates=self.design.candidates,
                        sample_index=sample_index,
                    )
                    if choice not in candidate_index:
                        raise ValueError(
                            f"Provider returned choice outside candidate set: {choice!r}"
                        )
                    observations.append(
                        CellObservation(
                            prefix_index=prefix_index,
                            context_index=context_index,
                            sample_index=sample_index,
                            choice_index=candidate_index[choice],
                        )
                    )
        return observations

    def analyze(
        self,
        provider: ChoiceProvider,
        observations: list[CellObservation],
    ) -> BlackBoxResult:
        counts = self._counts(observations)
        probabilities = counts / float(self.design.samples_per_cell)
        residuals = probabilities - probabilities.mean(axis=1, keepdims=True)
        aligned = residuals.mean(axis=0)
        statistic = float(np.square(aligned).sum())

        rng = np.random.default_rng(self.design.seed)
        null_statistics = np.empty(self.design.permutation_count, dtype=float)
        for permutation_index in range(self.design.permutation_count):
            permuted = np.empty_like(residuals)
            for prefix_index in range(len(self.design.prefixes)):
                order = rng.permutation(len(self.design.contexts))
                permuted[prefix_index] = residuals[prefix_index, order, :]
            null_aligned = permuted.mean(axis=0)
            null_statistics[permutation_index] = float(np.square(null_aligned).sum())

        exceedances = int(np.count_nonzero(null_statistics >= statistic))
        p_value = (exceedances + 1) / (self.design.permutation_count + 1)

        return BlackBoxResult(
            provider_id=provider.provider_id,
            model_id=provider.model_id,
            design_sha256=self.design.fingerprint(),
            observation_count=len(observations),
            statistic=statistic,
            p_value=p_value,
            significant=p_value <= self.design.alpha,
            alpha=self.design.alpha,
            permutation_count=self.design.permutation_count,
            context_candidate_residuals=aligned.tolist(),
        )

    def run(self, provider: ChoiceProvider) -> BlackBoxResult:
        return self.analyze(provider, self.collect(provider))

    def _counts(self, observations: list[CellObservation]) -> np.ndarray:
        expected = (
            len(self.design.prefixes)
            * len(self.design.contexts)
            * self.design.samples_per_cell
        )
        if len(observations) != expected:
            raise ValueError(
                f"Expected {expected} observations for complete design; "
                f"got {len(observations)}"
            )

        shape = (
            len(self.design.prefixes),
            len(self.design.contexts),
            len(self.design.candidates),
        )
        counts = np.zeros(shape, dtype=float)
        seen: set[tuple[int, int, int]] = set()

        for observation in observations:
            key = (
                observation.prefix_index,
                observation.context_index,
                observation.sample_index,
            )
            if key in seen:
                raise ValueError(f"Duplicate observation cell/sample: {key}")
            seen.add(key)

            if observation.prefix_index >= shape[0]:
                raise ValueError("Observation prefix index outside design")
            if observation.context_index >= shape[1]:
                raise ValueError("Observation context index outside design")
            if observation.choice_index >= shape[2]:
                raise ValueError("Observation choice index outside design")
            counts[
                observation.prefix_index,
                observation.context_index,
                observation.choice_index,
            ] += 1

        return counts


def blackbox_selftest(
    *,
    permutation_count: int = 499,
    samples_per_cell: int = 40,
    alpha: float = 0.01,
) -> BlackBoxSelfTestReport:
    design = BlackBoxDesign(
        prefixes=[
            "The requested answer is",
            "For this example choose",
            "The best matching word is",
            "Respond with exactly",
            "For consistency select",
            "The final answer should be",
            "Complete this using",
            "Choose one option only",
        ],
        contexts=[
            "context-731902",
            "context-846215",
            "context-294681",
            "context-503728",
            "context-918364",
            "context-167540",
            "context-625819",
            "context-380476",
        ],
        candidates=["amber", "berry", "cedar", "dune"],
        samples_per_cell=samples_per_cell,
        permutation_count=permutation_count,
        alpha=alpha,
        seed=20261004,
    )
    experiment = BlackBoxExperiment(design)
    off = experiment.run(
        SyntheticChoiceProvider(watermark_on=False, seed=design.seed)
    )
    on = experiment.run(
        SyntheticChoiceProvider(watermark_on=True, seed=design.seed)
    )
    return BlackBoxSelfTestReport(
        design_sha256=design.fingerprint(),
        off=off,
        on=on,
        validated=(not off.significant and on.significant),
    )
