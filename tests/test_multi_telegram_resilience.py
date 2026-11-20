import asyncio
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.error import BadRequest, Forbidden, NetworkError

MODULE_PATH = Path(__file__).resolve().parents[1] / "1.py"
SPEC = importlib.util.spec_from_file_location("rps_bot_telegram_resilience", MODULE_PATH)
bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bot)


def make_room():
    return {
        "host": 1,
        "players": [1, 2, 3],
        "names": {1: "A", 2: "B", 3: "C"},
        "messages": {1: 11, 2: 22, 3: 33},
        "capacity": 3,
        "status": "playing",
        "scores": {1: 0, 2: 0, 3: 0},
        "choices": {},
        "draws": 0,
        "round": 1,
        "round_token": "0123456789abcdef",
        "last_choices": {},
        "final_texts": {},
    }


def make_update(uid, choice, token="0123456789abcdef", answer=None):
    query = SimpleNamespace(
        data=f"multi_choice:deadbeef:{token}:{choice}",
        from_user=SimpleNamespace(id=uid, first_name=f"P{uid}"),
        answer=answer or AsyncMock(),
    )
    return SimpleNamespace(
        callback_query=query,
        effective_user=query.from_user,
        message=None,
    ), query


class TelegramResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_edit_ignores_not_modified_bad_request(self):
        bot_api = SimpleNamespace(
            edit_message_text=AsyncMock(side_effect=BadRequest("Message is not modified"))
        )
        await bot.safe_edit(bot_api, 1, 10, "same text")
        bot_api.edit_message_text.assert_awaited_once()

    async def test_safe_edit_suppresses_other_telegram_api_errors(self):
        for error in (BadRequest("message to edit not found"), NetworkError("network down"), Forbidden("bot was blocked")):
            with self.subTest(error=type(error).__name__):
                bot_api = SimpleNamespace(edit_message_text=AsyncMock(side_effect=error))
                await bot.safe_edit(bot_api, 1, 10, "updated text")
                bot_api.edit_message_text.assert_awaited_once()

    async def test_room_refresh_continues_after_individual_message_edit_errors(self):
        room = make_room()
        room["round_token"] = "0123456789abcdef"
        context = SimpleNamespace(bot_data={"multi_rooms": {"deadbeef": room}}, bot=object())

        with patch.object(
            bot, "safe_edit",
            new=AsyncMock(side_effect=[NetworkError("temporary outage"), None, None]),
        ) as edit:
            await bot.refresh_multi_room(context, "deadbeef")

        self.assertEqual(edit.await_count, 3)
        self.assertEqual(room["status"], "playing")

    async def test_simultaneous_choices_resolve_once_even_if_one_ack_fails(self):
        room = make_room()
        context = SimpleNamespace(
            bot_data={"multi_rooms": {"deadbeef": room}},
            bot=object(),
            application=SimpleNamespace(create_task=lambda *args, **kwargs: None),
        )
        updates = [
            make_update(1, "rock"),
            make_update(2, "scissors"),
            make_update(
                3, "scissors",
                answer=AsyncMock(side_effect=NetworkError("callback acknowledgement failed")),
            ),
        ]

        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)), \
             patch.object(bot, "safe_edit", new=AsyncMock()), \
             patch.object(bot, "schedule_multi_round_timeout") as schedule:
            await asyncio.gather(*(bot.multi_choice(update, context) for update, _ in updates))

        self.assertEqual(room["scores"], {1: 1, 2: 0, 3: 0})
        self.assertEqual(room["round"], 2)
        self.assertEqual(room["choices"], {})
        self.assertEqual(room["status"], "playing")
        schedule.assert_called_once_with(context, "deadbeef")

    async def test_duplicate_callbacks_from_same_player_only_register_one_choice(self):
        room = make_room()
        context = SimpleNamespace(
            bot_data={"multi_rooms": {"deadbeef": room}},
            bot=object(),
            application=SimpleNamespace(create_task=lambda *args, **kwargs: None),
        )
        updates = [
            make_update(1, "rock"),
            make_update(1, "paper"),
            make_update(2, "scissors"),
            make_update(3, "scissors"),
        ]

        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)), \
             patch.object(bot, "safe_edit", new=AsyncMock()), \
             patch.object(bot, "schedule_multi_round_timeout"):
            await asyncio.gather(*(bot.multi_choice(update, context) for update, _ in updates))

        self.assertEqual(room["scores"], {1: 1, 2: 0, 3: 0})
        self.assertEqual(room["round"], 2)

    async def test_stale_callback_is_rejected_without_recording_a_choice(self):
        room = make_room()
        context = SimpleNamespace(bot_data={"multi_rooms": {"deadbeef": room}}, bot=object())
        update, query = make_update(1, "rock", token="fedcba9876543210")

        with patch.object(bot, "is_member", new=AsyncMock(return_value=True)):
            await bot.multi_choice(update, context)

        self.assertEqual(room["choices"], {})
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs.get("show_alert"))


if __name__ == "__main__":
    unittest.main()
