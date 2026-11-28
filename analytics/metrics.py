"""Общие расчёты для ноутбука и графиков аналитики."""

from itertools import accumulate
from math import fsum


def pareto_metrics(revenues, threshold=0.8):
    """Возвращает доли пациентов, накопленные доли выручки и позицию порога."""
    ordered = sorted(revenues, reverse=True)
    total = fsum(ordered)
    if total <= 0:
        return [], [], None
    patients = [rank / len(ordered) for rank in range(len(ordered) + 1)]
    shares = [running / total for running in accumulate(ordered, initial=0)]
    shares[-1] = 1.0
    hit = next((rank for rank, share in enumerate(shares) if share >= threshold), None)
    return patients, shares, hit
