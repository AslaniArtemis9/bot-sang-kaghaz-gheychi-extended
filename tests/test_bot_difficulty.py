import unittest

from bot_strategy import choose_bot_move


BEATS = {
    "rock": "scissors",
    "scissors": "paper",
    "paper": "rock",
}


class FixedRandom:
    def __init__(self, choice_value="paper", random_value=0.0):
        self.choice_value = choice_value
        self.random_value = random_value

    def choice(self, values):
        if self.choice_value in values:
            return self.choice_value
        return values[0]

    def random(self):
        return self.random_value


class BotDifficultyTests(unittest.TestCase):
    def test_easy_is_random_and_does_not_need_history(self):
        rng = FixedRandom(choice_value="scissors")
        self.assertEqual(
            choose_bot_move("easy", ["rock", "rock"], BEATS, rng),
            "scissors",
        )

    def test_medium_counters_most_frequent_recent_move_half_the_time(self):
        rng = FixedRandom(random_value=0.2)
        self.assertEqual(
            choose_bot_move("medium", ["rock", "rock", "paper"], BEATS, rng),
            "paper",
        )

    def test_medium_can_still_choose_randomly(self):
        rng = FixedRandom(choice_value="scissors", random_value=0.8)
        self.assertEqual(
            choose_bot_move("medium", ["rock", "rock"], BEATS, rng),
            "scissors",
        )

    def test_hard_uses_prediction_more_often(self):
        rng = FixedRandom(random_value=0.8)
        self.assertEqual(
            choose_bot_move("hard", ["scissors", "scissors"], BEATS, rng),
            "rock",
        )

    def test_empty_history_falls_back_to_random_choice(self):
        rng = FixedRandom(choice_value="paper")
        self.assertEqual(choose_bot_move("hard", [], BEATS, rng), "paper")

    def test_only_five_most_recent_moves_are_used(self):
        rng = FixedRandom(random_value=0.0)
        history = ["rock", "rock", "rock", "rock", "rock", "scissors"]
        self.assertEqual(
            choose_bot_move("hard", history, BEATS, rng),
            "rock",
        )

    def test_invalid_difficulty_is_rejected(self):
        with self.assertRaises(ValueError):
            choose_bot_move("impossible", [], BEATS, FixedRandom())


if __name__ == "__main__":
    unittest.main()
