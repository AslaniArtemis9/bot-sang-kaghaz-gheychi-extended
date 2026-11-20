import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "1.py"
SPEC = importlib.util.spec_from_file_location("rps_bot_room_limits", MODULE_PATH)
bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bot)


def room(players=None, capacity=3, status="waiting"):
    players = players or [1]
    return {
        "host": players[0],
        "players": list(players),
        "names": {uid: f"P{uid}" for uid in players},
        "messages": {uid: uid * 10 for uid in players},
        "capacity": capacity,
        "status": status,
        "link": "https://t.me/example?start=mjoin_deadbeef",
    }


class MultiRoomBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def make_context(self, rooms):
        bot_api = SimpleNamespace(
            username="example_bot",
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=999)),
        )
        return SimpleNamespace(
            bot_data={"multi_rooms": rooms},
            bot=bot_api,
        )

    async def test_room_rejects_player_when_capacity_is_full(self):
        target = room([1, 2, 3], capacity=3)
        context = self.make_context({"deadbeef": target})

        await bot.join_multi_room(
            context, SimpleNamespace(id=4, first_name="P4"), "deadbeef"
        )

        self.assertEqual(target["players"], [1, 2, 3])
        context.bot.send_message.assert_awaited_once()
        self.assertIn("ظرفیت", context.bot.send_message.await_args.args[1])

    async def test_room_rejects_duplicate_member(self):
        target = room([1, 2], capacity=3)
        context = self.make_context({"deadbeef": target})

        await bot.join_multi_room(
            context, SimpleNamespace(id=2, first_name="P2"), "deadbeef"
        )

        self.assertEqual(target["players"], [1, 2])
        context.bot.send_message.assert_awaited_once()

    async def test_room_rejects_join_after_match_started(self):
        target = room([1, 2, 3], capacity=5, status="playing")
        context = self.make_context({"deadbeef": target})

        await bot.join_multi_room(
            context, SimpleNamespace(id=4, first_name="P4"), "deadbeef"
        )

        self.assertEqual(target["players"], [1, 2, 3])
        context.bot.send_message.assert_awaited_once()
        self.assertIn("دیگر پذیرای", context.bot.send_message.await_args.args[1])

    async def test_user_cannot_join_two_waiting_rooms(self):
        first = room([1, 2], capacity=5)
        second = room([3], capacity=5)
        context = self.make_context({"deadbeef": first, "cafebabe": second})

        await bot.join_multi_room(
            context, SimpleNamespace(id=2, first_name="P2"), "cafebabe"
        )

        self.assertEqual(first["players"], [1, 2])
        self.assertEqual(second["players"], [3])
        context.bot.send_message.assert_awaited_once()
        self.assertIn("ابتدا از اتاق", context.bot.send_message.await_args.args[1])

    async def test_valid_player_can_join_available_room(self):
        target = room([1], capacity=3)
        context = self.make_context({"deadbeef": target})

        with patch.object(bot, "refresh_multi_room", new=AsyncMock()):
            await bot.join_multi_room(
                context, SimpleNamespace(id=2, first_name="P2"), "deadbeef"
            )

        self.assertEqual(target["players"], [1, 2])
        self.assertEqual(target["names"][2], "P2")
        self.assertEqual(target["messages"][2], 999)

    async def test_existing_room_member_cannot_create_another_room(self):
        existing = room([7], capacity=4)
        context = self.make_context({"deadbeef": existing})
        query = SimpleNamespace(
            data="multi_cap:5",
            from_user=SimpleNamespace(id=7, first_name="P7"),
            message=SimpleNamespace(message_id=70),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=query.from_user,
            message=None,
        )

        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)):
            await bot.multi_create(update, context)

        self.assertEqual(set(context.bot_data["multi_rooms"]), {"deadbeef"})
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))


if __name__ == "__main__":
    unittest.main()
