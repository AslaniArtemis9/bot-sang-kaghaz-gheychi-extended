import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "1.py"
SPEC = importlib.util.spec_from_file_location("rps_bot_multi_scoring", MODULE_PATH)
bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bot)


class MultiMatchScoringTests(unittest.IsolatedAsyncioTestCase):
    def make_room(self, choices, scores=None):
        players = [1, 2, 3]
        return {
            "players": players,
            "names": {1: "A", 2: "B", 3: "C"},
            "messages": {1: 11, 2: 22, 3: 33},
            "status": "playing",
            "scores": scores or {1: 0, 2: 0, 3: 0},
            "choices": dict(choices),
            "draws": 0,
            "round": 1,
            "round_token": "round-token",
            "last_choices": {},
            "final_texts": {},
        }

    def make_context(self, room):
        return SimpleNamespace(
            bot_data={"multi_rooms": {"deadbeef": room}},
            bot=SimpleNamespace(),
            application=SimpleNamespace(create_task=lambda *args, **kwargs: None),
        )

    async def test_winning_move_group_scores_for_every_member(self):
        room = self.make_room({1: "rock", 2: "rock", 3: "scissors"})
        context = self.make_context(room)

        with patch.object(bot, "schedule_multi_round_timeout"), \
             patch.object(bot, "safe_edit", new=AsyncMock()), \
             patch.object(bot, "record_result") as record:
            await bot.resolve_multi_round(
                context, "deadbeef", expected_token="round-token"
            )

        self.assertEqual(room["scores"], {1: 1, 2: 1, 3: 0})
        self.assertEqual(room["round"], 2)
        self.assertEqual(room["last_choices"], {1: "rock", 2: "rock", 3: "scissors"})
        self.assertEqual(room["draws"], 0)
        record.assert_not_called()

    async def test_all_same_move_increments_draw_count_without_points(self):
        room = self.make_room({1: "paper", 2: "paper", 3: "paper"})
        context = self.make_context(room)

        with patch.object(bot, "schedule_multi_round"), \
             patch.object(bot, "safe_edit", new=AsyncMock()):
            await bot.resolve_multi_round(
                context, "deadbeef", expected_token="round-token"
            )

        self.assertEqual(room["scores"], {1: 0, 2: 0, 3: 0})
        self.assertEqual(room["draws"], 1)
        self.assertEqual(room["round"], 2)

    async def test_all_three_moves_increments_draw_count_without_points(self):
        room = self.make_room({1: "rock", 2: "paper", 3: "scissors"})
        context = self.make_context(room)

        with patch.object(bot, "schedule_multi_round_timeout"), \
             patch.object(bot, "safe_edit", new=AsyncMock()):
            await bot.resolve_multi_round(
                context, "deadbeef", expected_token="round-token"
            )

        self.assertEqual(room["scores"], {1: 0, 2: 0, 3: 0})
        self.assertEqual(room["draws"], 1)
        self.assertEqual(room["round"], 2)

    async def test_match_finishes_and_records_winner_and_loser(self):
        room = self.make_room(
            {1: "rock", 2: "rock", 3: "scissors"},
            scores={1: 2, 2: 0, 3: 0},
        )
        context = self.make_context(room)

        with patch.object(bot, "refresh_multi_room", new=AsyncMock()) as refresh, \
             patch.object(bot, "record_result") as record:
            await bot.resolve_multi_round(
                context, "deadbeef", expected_token="round-token"
            )

        self.assertEqual(room["status"], "finished")
        self.assertEqual(room["scores"], {1: 3, 2: 1, 3: 0})
        self.assertNotIn("deadbeef", context.bot_data["multi_rooms"])
        self.assertIn("برنده", room["final_texts"][1])
        self.assertEqual(
            record.call_args_list,
            [
                call(1, "A", won=True),
                call(2, "B", won=False),
                call(3, "C", won=False),
            ],
        )
        refresh.assert_awaited_once_with(context, "deadbeef")

    async def test_simultaneous_champions_are_all_recorded_as_winners(self):
        room = self.make_room(
            {1: "rock", 2: "rock", 3: "scissors"},
            scores={1: 2, 2: 2, 3: 0},
        )
        context = self.make_context(room)

        with patch.object(bot, "refresh_multi_room", new=AsyncMock()), \
             patch.object(bot, "record_result") as record:
            await bot.resolve_multi_round(
                context, "deadbeef", expected_token="round-token"
            )

        self.assertEqual(room["scores"], {1: 3, 2: 3, 3: 0})
        self.assertIn("A", room["final_texts"][1])
        self.assertIn("B", room["final_texts"][1])
        self.assertEqual(
            record.call_args_list,
            [
                call(1, "A", won=True),
                call(2, "B", won=True),
                call(3, "C", won=False),
            ],
        )

    async def test_timeout_sole_responder_can_finish_match(self):
        room = self.make_room(
            {2: "paper"},
            scores={1: 0, 2: 2, 3: 0},
        )
        context = self.make_context(room)

        with patch.object(bot, "refresh_multi_room", new=AsyncMock()), \
             patch.object(bot, "record_result") as record:
            await bot.resolve_multi_round(
                context, "deadbeef", timed_out=True,
                expected_token="round-token",
            )

        self.assertEqual(room["status"], "finished")
        self.assertEqual(room["scores"][2], 3)
        self.assertEqual(
            record.call_args_list,
            [
                call(1, "A", won=False),
                call(2, "B", won=True),
                call(3, "C", won=False),
            ],
        )


if __name__ == "__main__":
    unittest.main()
