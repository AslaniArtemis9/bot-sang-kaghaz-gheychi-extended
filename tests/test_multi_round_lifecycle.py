import asyncio
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "1.py"
SPEC = importlib.util.spec_from_file_location("rps_bot", MODULE_PATH)
bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bot)


class MultiRoundLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def make_context(self, room):
        return SimpleNamespace(
            bot_data={"multi_rooms": {"deadbeef": room}},
            bot=SimpleNamespace(),
            application=SimpleNamespace(create_task=lambda *args, **kwargs: None),
        )

    def make_room(self, choices=None, scores=None):
        players = [1, 2, 3]
        return {
            "players": players,
            "names": {1: "A", 2: "B", 3: "C"},
            "messages": {1: 11, 2: 22, 3: 33},
            "status": "playing",
            "scores": scores or {1: 0, 2: 0, 3: 0},
            "choices": choices or {},
            "draws": 0,
            "round": 1,
            "round_token": "old-round-token",
            "last_choices": {},
            "final_texts": {},
        }

    async def test_timeout_awards_sole_responder_and_starts_next_round(self):
        room = self.make_room({2: "paper"})
        context = self.make_context(room)

        with patch.object(bot, "schedule_multi_round_timeout") as schedule, \
             patch.object(bot, "safe_edit", new=AsyncMock()):
            await bot.resolve_multi_round(
                context, "deadbeef", timed_out=True,
                expected_token="old-round-token",
            )

        self.assertEqual(room["scores"], {1: 0, 2: 1, 3: 0})
        self.assertEqual(room["round"], 2)
        self.assertEqual(room["choices"], {})
        self.assertEqual(room["status"], "playing")
        schedule.assert_called_once_with(context, "deadbeef")

    async def test_timeout_with_no_responses_closes_room_without_stats(self):
        room = self.make_room()
        context = self.make_context(room)

        with patch.object(bot, "refresh_multi_room", new=AsyncMock()) as refresh, \
             patch.object(bot, "record_result") as record:
            await bot.resolve_multi_round(
                context, "deadbeef", timed_out=True,
                expected_token="old-round-token",
            )

        self.assertEqual(room["status"], "finished")
        self.assertNotIn("deadbeef", context.bot_data["multi_rooms"])
        refresh.assert_awaited_once_with(context, "deadbeef")
        record.assert_not_called()

    async def test_stale_round_token_cannot_change_game(self):
        room = self.make_room({1: "rock"})
        context = self.make_context(room)

        with patch.object(bot, "safe_edit", new=AsyncMock()) as edit, \
             patch.object(bot, "schedule_multi_round_timeout") as schedule:
            await bot.resolve_multi_round(
                context, "deadbeef", timed_out=True,
                expected_token="stale-token",
            )

        self.assertEqual(room["round"], 1)
        self.assertEqual(room["scores"], {1: 0, 2: 0, 3: 0})
        self.assertEqual(room["round_token"], "old-round-token")
        edit.assert_not_awaited()
        schedule.assert_not_called()

    async def test_two_resolvers_cannot_score_the_same_round_twice(self):
        room = self.make_room({
            1: "rock",
            2: "scissors",
            3: "scissors",
        })
        context = self.make_context(room)

        async def pause_edit(*args, **kwargs):
            await asyncio.sleep(0)

        with patch.object(bot, "safe_edit", new=AsyncMock(side_effect=pause_edit)), \
             patch.object(bot, "schedule_multi_round_timeout") as schedule:
            await asyncio.gather(
                bot.resolve_multi_round(
                    context, "deadbeef",
                    expected_token="old-round-token",
                ),
                bot.resolve_multi_round(
                    context, "deadbeef", timed_out=True,
                    expected_token="old-round-token",
                ),
            )

        self.assertEqual(room["scores"], {1: 1, 2: 0, 3: 0})
        self.assertEqual(room["round"], 2)
        schedule.assert_called_once_with(context, "deadbeef")

    async def test_timeout_task_ignores_replaced_round_token(self):
        room = self.make_room({1: "rock"})
        room["round_token"] = "new-round-token"
        context = self.make_context(room)

        with patch.object(bot.asyncio, "sleep", new=AsyncMock()), \
             patch.object(bot, "resolve_multi_round", new=AsyncMock()) as resolve:
            await bot.multi_round_timeout(
                context, "deadbeef", "old-round-token"
            )

        resolve.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
