import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "1.py"
SPEC = importlib.util.spec_from_file_location("rps_bot_modes", MODULE_PATH)
bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bot)


class GameModeIsolationTests(unittest.IsolatedAsyncioTestCase):
    def make_context(self):
        return SimpleNamespace(
            user_data={},
            bot_data={},
        )

    def test_solo_mode_state_is_user_scoped_and_separate(self):
        context = self.make_context()
        match = bot.get_bot_match(context)
        match["user"] = 2

        self.assertEqual(context.user_data["bot_match"]["user"], 2)
        self.assertNotIn("games", context.bot_data)
        self.assertNotIn("multi_rooms", context.bot_data)

    def test_friend_and_multiplayer_use_distinct_state_containers(self):
        context = self.make_context()
        friend_games = bot.get_games(context)
        multi_rooms = bot.get_multi_rooms(context)

        friend_games["friend-id"] = {"status": "playing"}
        multi_rooms["multi-id"] = {"status": "playing"}

        self.assertIsNot(friend_games, multi_rooms)
        self.assertIn("friend-id", friend_games)
        self.assertNotIn("friend-id", multi_rooms)
        self.assertIn("multi-id", multi_rooms)
        self.assertNotIn("multi-id", friend_games)

    def test_friend_game_blocks_entry_to_other_competitive_modes(self):
        context = self.make_context()
        bot.get_user_game(context)[42] = "friend-id"
        self.assertTrue(bot.user_has_active_competitive_game(context, 42))
        self.assertFalse(bot.user_has_active_competitive_game(context, 99))

    def test_private_multi_room_blocks_entry_to_other_competitive_modes(self):
        context = self.make_context()
        bot.get_multi_rooms(context)["multi-id"] = {
            "players": [42],
            "status": "playing",
        }
        self.assertTrue(bot.user_has_active_competitive_game(context, 42))
        self.assertFalse(bot.user_has_active_competitive_game(context, 99))

    def test_group_two_player_blocks_entry_to_other_competitive_modes(self):
        context = self.make_context()
        bot.get_group_two_user_game(context)[42] = -100123
        self.assertTrue(bot.user_has_active_competitive_game(context, 42))
        self.assertFalse(bot.user_has_active_competitive_game(context, 99))

    async def test_joining_friend_game_does_not_end_an_existing_competition(self):
        context = self.make_context()
        context.bot_data.update({
            "games": {
                "friend-target": {
                    "players": [10], "status": "waiting",
                    "names": {10: "Host"}, "scores": {10: 0},
                    "choices": {}, "draws": 0, "round": 1, "msgs": {10: 1},
                }
            },
            "multi_rooms": {"multi-active": {"players": [42], "status": "playing"}},
        })
        user = SimpleNamespace(id=42, first_name="Guest")
        context.bot = SimpleNamespace(send_message=AsyncMock())
        with patch.object(bot, "safe_edit", new=AsyncMock()) as safe_edit:
            await bot.join_game(context, user, "friend-target")
        self.assertEqual(context.bot_data["games"]["friend-target"]["players"], [10])
        self.assertEqual(context.bot_data["multi_rooms"]["multi-active"]["players"], [42])
        context.bot.send_message.assert_awaited_once()
        safe_edit.assert_not_awaited()

    async def test_play_friend_rejects_conflicting_match_with_one_callback_answer(self):
        context = self.make_context()
        context.bot_data["multi_rooms"] = {
            "active": {"players": [42], "status": "playing"}
        }
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=42, first_name="Guest"),
            message=SimpleNamespace(message_id=77),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query, effective_user=query.from_user)
        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)):
            await bot.play_friend(update, context)
        query.answer.assert_awaited_once_with(
            "شما از قبل در یک مسابقهٔ دیگر شرکت دارید؛ ابتدا آن را تمام کنید.",
            show_alert=True,
        )
        query.edit_message_text.assert_not_awaited()
        self.assertEqual(bot.get_games(context), {})

    async def test_nonparticipant_cannot_end_friend_game(self):
        game = {
            "players": [10, 20],
            "status": "playing",
            "scores": {10: 0, 20: 0},
            "names": {10: "A", 20: "B"},
            "draws": 0,
            "round": 1,
            "choices": {},
            "msgs": {10: 100, 20: 200},
        }
        context = SimpleNamespace(bot_data={"games": {"1234abcd": game}}, bot=object())
        query = SimpleNamespace(
            data="fr_end:1234abcd",
            from_user=SimpleNamespace(id=99),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query, effective_user=query.from_user)

        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)):
            await bot.friend_end(update, context)

        self.assertIn("1234abcd", context.bot_data["games"])
        self.assertEqual(query.answer.await_count, 2)
        self.assertEqual(
            query.answer.await_args_list[-1].args,
            ("شما عضو این بازی نیستید.",),
        )
        self.assertEqual(
            query.answer.await_args_list[-1].kwargs,
            {"show_alert": True},
        )

    async def test_participant_can_end_friend_game(self):
        game = {
            "players": [10, 20],
            "status": "playing",
            "scores": {10: 0, 20: 0},
            "names": {10: "A", 20: "B"},
            "draws": 0,
            "round": 1,
            "choices": {},
            "msgs": {10: 100, 20: 200},
        }
        context = SimpleNamespace(bot_data={"games": {"1234abcd": game}}, bot=object())
        query = SimpleNamespace(
            data="fr_end:1234abcd",
            from_user=SimpleNamespace(id=10),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query, effective_user=query.from_user)

        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)):
            with patch.object(bot, "end_game", new=AsyncMock()) as end_game:
                await bot.friend_end(update, context)

        end_game.assert_awaited_once_with(context, "1234abcd")


if __name__ == "__main__":
    unittest.main()
