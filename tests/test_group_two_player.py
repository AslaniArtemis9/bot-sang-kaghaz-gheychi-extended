import asyncio
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.error import NetworkError

MODULE_PATH = Path(__file__).resolve().parents[1] / "1.py"
SPEC = importlib.util.spec_from_file_location("rps_bot_group_two", MODULE_PATH)
bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bot)


class GroupTwoPlayerTests(unittest.IsolatedAsyncioTestCase):
    def make_game(self, choices=None, scores=None):
        return {
            "gid": "deadbeef",
            "chat_id": -100123,
            "message_id": 55,
            "host": 1,
            "players": [1, 2],
            "names": {1: "A", 2: "B"},
            "scores": scores or {1: 0, 2: 0},
            "choices": choices or {},
            "draws": 0,
            "round": 1,
            "round_token": "abcdef0123456789",
            "round_note": "",
            "status": "playing",
        }

    def make_context(self, game):
        return SimpleNamespace(
            bot_data={
                "group_two_games": {-100123: game},
                "group_two_user_game": {1: -100123, 2: -100123},
            },
            bot=SimpleNamespace(),
            application=SimpleNamespace(create_task=lambda *args, **kwargs: None),
        )

    def test_group_state_is_separate_from_private_and_multi_modes(self):
        context = SimpleNamespace(bot_data={})
        group_games = bot.get_group_two_games(context)
        friend_games = bot.get_games(context)
        multi_rooms = bot.get_multi_rooms(context)
        group_games[-100123] = {"status": "playing"}
        self.assertIsNot(group_games, friend_games)
        self.assertIsNot(group_games, multi_rooms)
        self.assertNotIn(-100123, friend_games)
        self.assertNotIn(-100123, multi_rooms)

    async def test_second_member_joins_and_starts_match(self):
        game = {
            "gid": "deadbeef",
            "chat_id": -100123,
            "message_id": 55,
            "host": 1,
            "players": [1],
            "names": {1: "A"},
            "scores": {1: 0},
            "choices": {},
            "draws": 0,
            "round": 1,
            "round_token": None,
            "round_note": "",
            "status": "waiting",
        }
        context = SimpleNamespace(
            bot_data={
                "group_two_games": {-100123: game},
                "group_two_user_game": {1: -100123},
            },
            bot=SimpleNamespace(),
            application=SimpleNamespace(create_task=lambda *args, **kwargs: None),
        )
        query = SimpleNamespace(
            data="g2_join:deadbeef",
            from_user=SimpleNamespace(id=2, first_name="B"),
            answer=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=query.from_user,
            effective_chat=SimpleNamespace(id=-100123, type="supergroup"),
        )
        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)), \
             patch.object(bot, "schedule_group_two_timeout") as schedule, \
             patch.object(bot, "refresh_group_two_game", new=AsyncMock()):
            await bot.group_two_join(update, context)
        self.assertEqual(game["players"], [1, 2])
        self.assertEqual(game["status"], "playing")
        self.assertEqual(game["scores"], {1: 0, 2: 0})
        self.assertEqual(context.bot_data["group_two_user_game"][2], -100123)
        schedule.assert_called_once_with(context, -100123)

    async def test_non_player_cannot_submit_move(self):
        game = self.make_game()
        context = self.make_context(game)
        query = SimpleNamespace(
            data="g2_choice:deadbeef:abcdef0123456789:rock",
            from_user=SimpleNamespace(id=99),
            answer=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=query.from_user,
            effective_chat=SimpleNamespace(id=-100123, type="group"),
        )
        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)):
            await bot.group_two_choice(update, context)
        self.assertEqual(game["choices"], {})
        query.answer.assert_awaited_once()

    async def test_duplicate_move_is_rejected(self):
        game = self.make_game({1: "rock"})
        context = self.make_context(game)
        query = SimpleNamespace(
            data="g2_choice:deadbeef:abcdef0123456789:paper",
            from_user=SimpleNamespace(id=1),
            answer=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=query.from_user,
            effective_chat=SimpleNamespace(id=-100123, type="group"),
        )
        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)):
            await bot.group_two_choice(update, context)
        self.assertEqual(game["choices"], {1: "rock"})
        query.answer.assert_awaited_once_with("انتخابت قبلاً ثبت شده است.", show_alert=True)

    async def test_both_choices_resolve_and_award_point_once(self):
        game = self.make_game({1: "rock", 2: "scissors"})
        context = self.make_context(game)
        with patch.object(bot, "safe_edit", new=AsyncMock()), \
             patch.object(bot, "schedule_group_two_timeout") as schedule:
            await bot.resolve_group_two_round(
                context, -100123, expected_token="abcdef0123456789"
            )
            await bot.resolve_group_two_round(
                context, -100123, timed_out=True,
                expected_token="abcdef0123456789"
            )
        self.assertEqual(game["scores"], {1: 1, 2: 0})
        self.assertEqual(game["round"], 2)
        self.assertEqual(game["choices"], {})
        schedule.assert_called_once_with(context, -100123)

    async def test_timeout_awards_round_to_only_responder(self):
        game = self.make_game({2: "paper"})
        context = self.make_context(game)
        with patch.object(bot, "safe_edit", new=AsyncMock()), \
             patch.object(bot, "schedule_group_two_timeout"):
            await bot.resolve_group_two_round(
                context, -100123, timed_out=True,
                expected_token="abcdef0123456789"
            )
        self.assertEqual(game["scores"], {1: 0, 2: 1})
        self.assertIn("انتخاب نکرد", game["round_note"])

    async def test_timeout_with_no_choices_closes_match(self):
        game = self.make_game()
        context = self.make_context(game)
        with patch.object(bot, "safe_edit", new=AsyncMock()), \
             patch.object(bot, "record_result") as record:
            await bot.resolve_group_two_round(
                context, -100123, timed_out=True,
                expected_token="abcdef0123456789"
            )
        self.assertNotIn(-100123, context.bot_data["group_two_games"])
        self.assertEqual(context.bot_data["group_two_user_game"], {})
        record.assert_not_called()

    async def test_final_score_records_winner_and_loser(self):
        game = self.make_game(
            {1: "rock", 2: "scissors"},
            scores={1: 2, 2: 0},
        )
        context = self.make_context(game)
        with patch.object(bot, "safe_edit", new=AsyncMock()), \
             patch.object(bot, "record_result") as record:
            await bot.resolve_group_two_round(
                context, -100123, expected_token="abcdef0123456789"
            )
        self.assertNotIn(-100123, context.bot_data["group_two_games"])
        self.assertEqual(record.call_count, 2)
        record.assert_any_call(1, "A", won=True)
        record.assert_any_call(2, "B", won=False)

    async def test_stale_timeout_cannot_resolve_new_round(self):
        game = self.make_game({1: "rock"})
        game["round_token"] = "0123456789abcdef"
        context = self.make_context(game)
        with patch.object(bot, "safe_edit", new=AsyncMock()) as edit:
            await bot.resolve_group_two_round(
                context, -100123, timed_out=True,
                expected_token="abcdef0123456789"
            )
        self.assertEqual(game["round"], 1)
        self.assertEqual(game["scores"], {1: 0, 2: 0})
        edit.assert_not_awaited()

    async def test_join_state_refreshes_when_callback_ack_fails(self):
        game = {
            "gid": "deadbeef",
            "chat_id": -100123,
            "message_id": 55,
            "host": 1,
            "players": [1],
            "names": {1: "A"},
            "scores": {1: 0},
            "choices": {},
            "draws": 0,
            "round": 1,
            "round_token": None,
            "round_note": "",
            "status": "waiting",
        }
        context = SimpleNamespace(
            bot_data={
                "group_two_games": {-100123: game},
                "group_two_user_game": {1: -100123},
            },
            bot=SimpleNamespace(),
            application=SimpleNamespace(create_task=lambda *args, **kwargs: None),
        )
        query = SimpleNamespace(
            data="g2_join:deadbeef",
            from_user=SimpleNamespace(id=2, first_name="B"),
            answer=AsyncMock(side_effect=NetworkError("callback acknowledgement failed")),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=query.from_user,
            effective_chat=SimpleNamespace(id=-100123, type="supergroup"),
        )
        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)), \\
             patch.object(bot, "schedule_group_two_timeout"), \\
             patch.object(bot, "refresh_group_two_game", new=AsyncMock()) as refresh:
            await bot.group_two_join(update, context)
        self.assertEqual(game["players"], [1, 2])
        self.assertEqual(game["status"], "playing")
        refresh.assert_awaited_once_with(context, -100123)

    async def test_choice_resolves_when_callback_ack_fails(self):
        game = self.make_game({1: "rock"})
        context = self.make_context(game)
        query = SimpleNamespace(
            data="g2_choice:deadbeef:abcdef0123456789:scissors",
            from_user=SimpleNamespace(id=2),
            answer=AsyncMock(side_effect=NetworkError("callback acknowledgement failed")),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=query.from_user,
            effective_chat=SimpleNamespace(id=-100123, type="group"),
        )
        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)), \\
             patch.object(bot, "safe_edit", new=AsyncMock()), \\
             patch.object(bot, "schedule_group_two_timeout"):
            await bot.group_two_choice(update, context)
        self.assertEqual(game["scores"], {1: 1, 2: 0})
        self.assertEqual(game["round"], 2)
        self.assertEqual(game["choices"], {})

    async def test_end_cleans_up_when_callback_ack_fails(self):
        game = self.make_game()
        context = self.make_context(game)
        query = SimpleNamespace(
            data="g2_end:deadbeef",
            from_user=SimpleNamespace(id=1),
            answer=AsyncMock(side_effect=NetworkError("callback acknowledgement failed")),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=query.from_user,
            effective_chat=SimpleNamespace(id=-100123, type="group"),
        )
        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)), \\
             patch.object(bot, "safe_edit", new=AsyncMock()), \\
             patch.object(bot, "record_result") as record:
            await bot.group_two_end(update, context)
        self.assertNotIn(-100123, context.bot_data["group_two_games"])
        self.assertEqual(context.bot_data["group_two_user_game"], {})
        self.assertEqual(record.call_count, 2)

    async def test_non_member_callback_does_not_replace_group_message(self):
        game = self.make_game()
        context = self.make_context(game)
        query = SimpleNamespace(
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=3),
            effective_chat=SimpleNamespace(id=-100123, type="group"),
            message=None,
        )
        with patch.object(bot, "is_member", new=AsyncMock(return_value=False)):
            await bot.group_two_choice(update, context)
        query.answer.assert_awaited_once()
        query.edit_message_text.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
