import unittest

from game_logic import evaluate_multi_round


BEATS = {
    "rock": "scissors",
    "scissors": "paper",
    "paper": "rock",
}


class MultiplayerRoundTests(unittest.TestCase):
    def test_rock_group_beats_scissors_group(self):
        winners = evaluate_multi_round(
            [1, 2, 3, 4],
            {1: "rock", 2: "rock", 3: "scissors", 4: "scissors"},
            BEATS,
        )
        self.assertEqual(winners, {1, 2})

    def test_paper_beats_rock(self):
        winners = evaluate_multi_round(
            [1, 2, 3],
            {1: "paper", 2: "rock", 3: "paper"},
            BEATS,
        )
        self.assertEqual(winners, {1, 3})

    def test_scissors_beats_paper(self):
        winners = evaluate_multi_round(
            [1, 2, 3],
            {1: "scissors", 2: "paper", 3: "scissors"},
            BEATS,
        )
        self.assertEqual(winners, {1, 3})

    def test_all_same_move_is_draw(self):
        winners = evaluate_multi_round(
            [1, 2, 3], {1: "rock", 2: "rock", 3: "rock"}, BEATS
        )
        self.assertEqual(winners, set())

    def test_all_three_moves_is_draw(self):
        winners = evaluate_multi_round(
            [1, 2, 3],
            {1: "rock", 2: "paper", 3: "scissors"},
            BEATS,
        )
        self.assertEqual(winners, set())

    def test_only_responder_wins_when_others_timeout(self):
        winners = evaluate_multi_round(
            [1, 2, 3], {2: "paper"}, BEATS
        )
        self.assertEqual(winners, {2})

    def test_two_same_responders_and_one_timeout_is_not_a_point(self):
        winners = evaluate_multi_round(
            [1, 2, 3], {1: "scissors", 2: "scissors"}, BEATS
        )
        self.assertEqual(winners, set())

    def test_no_responses_has_no_winner(self):
        winners = evaluate_multi_round([1, 2, 3], {}, BEATS)
        self.assertEqual(winners, set())


if __name__ == "__main__":
    unittest.main()
