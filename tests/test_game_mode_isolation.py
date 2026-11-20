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
        context = SimpleNamespace(bot_data={"games": {"1234abcd": game}})
        query = SimpleNamespace(
            data="fr_end:1234abcd",
            from_user=SimpleNamespace(id=99),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)

        await bot.friend_end(update, context)

        self.assertIn("1234abcd", context.bot_data["games"])
        query.answer.assert_awaited_once_with(
            "شما عضو این بازی نیستید.", show_alert=True
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
        context = SimpleNamespace(bot_data={"games": {"1234abcd": game}})
        query = SimpleNamespace(
            data="fr_end:1234abcd",
            from_user=SimpleNamespace(id=10),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)

        with patch.object(bot, "end_game", new=AsyncMock()) as end_game:
            await bot.friend_end(update, context)

        end_game.assert_awaited_once_with(context, "1234abcd")


if __name__ == "__main__":
    unittest.main()
