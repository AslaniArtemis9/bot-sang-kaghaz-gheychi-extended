import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "1.py"
SPEC = importlib.util.spec_from_file_location("rps_bot_room_controls", MODULE_PATH)
bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bot)


def make_room(status="waiting"):
    return {
        "host": 1,
        "players": [1, 2, 3],
        "names": {1: "A", 2: "B", 3: "C"},
        "messages": {1: 11, 2: 22, 3: 33},
        "capacity": 5,
        "status": status,
        "link": "https://t.me/example?start=mjoin_deadbeef",
    }


class MultiRoomControlTests(unittest.IsolatedAsyncioTestCase):
    def make_context(self, room):
        return SimpleNamespace(
            bot_data={"multi_rooms": {"deadbeef": room}},
            bot=SimpleNamespace(),
            application=SimpleNamespace(create_task=lambda *args, **kwargs: None),
        )

    def make_update(self, callback, uid, data):
        query = SimpleNamespace(
            data=data,
            from_user=SimpleNamespace(id=uid, first_name=f"P{uid}"),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=query.from_user,
            message=None,
        )
        return update, query

    async def invoke(self, handler, update, context, **patches):
        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)):
            with patches.pop("extra", patch.object(bot, "safe_edit", new=AsyncMock())):
                with patches.pop("refresh", patch.object(bot, "refresh_multi_room", new=AsyncMock())) as refresh:
                    with patches.pop("schedule", patch.object(bot, "schedule_multi_round_timeout")) as schedule:
                        with patches.pop("record", patch.object(bot, "record_result")) as record:
                            await handler(update, context)
        return refresh, schedule, record

    async def test_only_host_can_start_match(self):
        room = make_room()
        context = self.make_context(room)
        update, query = self.make_update("multi_start:deadbeef", 2, "multi_start:deadbeef")

        await self.invoke(bot.multi_start, update, context)

        self.assertEqual(room["status"], "waiting")
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))

    async def test_host_cannot_start_with_fewer_than_three_players(self):
        room = make_room()
        room["players"] = [1, 2]
        context = self.make_context(room)
        update, query = self.make_update("multi_start:deadbeef", 1, "multi_start:deadbeef")

        await self.invoke(bot.multi_start, update, context)

        self.assertEqual(room["status"], "waiting")
        self.assertIn("حداقل ۳ نفر", query.answer.await_args.args[0])

    async def test_host_can_start_valid_match_and_initializes_state(self):
        room = make_room()
        context = self.make_context(room)
        update, query = self.make_update("multi_start:deadbeef", 1, "multi_start:deadbeef")

        refresh, schedule, _ = await self.invoke(bot.multi_start, update, context)

        self.assertEqual(room["status"], "playing")
        self.assertEqual(room["scores"], {1: 0, 2: 0, 3: 0})
        self.assertEqual(room["choices"], {})
        self.assertEqual(room["round"], 1)
        schedule.assert_called_once_with(context, "deadbeef")
        refresh.assert_awaited_once_with(context, "deadbeef")

    async def test_host_cannot_leave_waiting_room(self):
        room = make_room()
        context = self.make_context(room)
        update, query = self.make_update("multi_leave:deadbeef", 1, "multi_leave:deadbeef")

        await self.invoke(bot.multi_leave, update, context)

        self.assertEqual(room["players"], [1, 2, 3])
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))

    async def test_nonmember_cannot_leave_room(self):
        room = make_room()
        context = self.make_context(room)
        update, query = self.make_update("multi_leave:deadbeef", 99, "multi_leave:deadbeef")

        await self.invoke(bot.multi_leave, update, context)

        self.assertEqual(room["players"], [1, 2, 3])
        self.assertIn("عضو این اتاق نیستید", query.answer.await_args.args[0])

    async def test_member_can_leave_waiting_room(self):
        room = make_room()
        context = self.make_context(room)
        update, query = self.make_update("multi_leave:deadbeef", 2, "multi_leave:deadbeef")

        refresh, _, _ = await self.invoke(bot.multi_leave, update, context)

        self.assertEqual(room["players"], [1, 3])
        self.assertNotIn(2, room["names"])
        self.assertNotIn(2, room["messages"])
        query.edit_message_text.assert_awaited_once()
        refresh.assert_awaited_once_with(context, "deadbeef")

    async def test_player_cannot_leave_after_match_started(self):
        room = make_room(status="playing")
        context = self.make_context(room)
        update, query = self.make_update("multi_leave:deadbeef", 2, "multi_leave:deadbeef")

        await self.invoke(bot.multi_leave, update, context)

        self.assertEqual(room["players"], [1, 2, 3])
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))

    async def test_nonhost_cannot_cancel_room(self):
        room = make_room()
        context = self.make_context(room)
        update, query = self.make_update("multi_cancel:deadbeef", 2, "multi_cancel:deadbeef")

        await self.invoke(bot.multi_cancel, update, context)

        self.assertIn("deadbeef", context.bot_data["multi_rooms"])
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))

    async def test_host_cannot_cancel_after_match_started(self):
        room = make_room(status="playing")
        context = self.make_context(room)
        update, query = self.make_update("multi_cancel:deadbeef", 1, "multi_cancel:deadbeef")

        await self.invoke(bot.multi_cancel, update, context)

        self.assertIn("deadbeef", context.bot_data["multi_rooms"])
        self.assertEqual(room["status"], "playing")
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))

    async def test_host_cancel_removes_room_and_notifies_all_members(self):
        room = make_room()
        context = self.make_context(room)
        update, query = self.make_update("multi_cancel:deadbeef", 1, "multi_cancel:deadbeef")

        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)), \
             patch.object(bot, "safe_edit", new=AsyncMock()) as safe_edit:
            await bot.multi_cancel(update, context)

        self.assertNotIn("deadbeef", context.bot_data["multi_rooms"])
        self.assertEqual(safe_edit.await_count, 3)
        self.assertEqual(
            [c.args[1] for c in safe_edit.await_args_list],
            [1, 2, 3],
        )


if __name__ == "__main__":
    unittest.main()
