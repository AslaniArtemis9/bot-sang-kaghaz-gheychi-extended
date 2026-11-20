"""Difficulty-aware move selection for the single-player bot."""

import random
from collections import Counter


def choose_bot_move(difficulty, history, beats, rng=random):
    """Choose a move using only the player's previous moves.

    Medium counters a simple recent-frequency prediction half the time;
    hard does so 85% of the time. Both retain randomness, so the bot is
    not guaranteed to predict correctly.
    """
    if difficulty not in {"easy", "medium", "hard"}:
        raise ValueError("difficulty must be easy, medium, or hard")

    choices = tuple(beats)
    if difficulty == "easy":
        return rng.choice(choices)

    recent = [move for move in history[-5:] if move in beats]
    if not recent:
        return rng.choice(choices)

    counts = Counter(recent)
    highest = max(counts.values())
    most_common = [move for move, count in counts.items() if count == highest]
    predicted = rng.choice(most_common)

    prediction_probability = 0.5 if difficulty == "medium" else 0.85
    if rng.random() < prediction_probability:
        counters = {
            losing_move: winning_move
            for winning_move, losing_move in beats.items()
        }
        return counters[predicted]

    return rng.choice(choices)
