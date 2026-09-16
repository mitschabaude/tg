import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import datetime, timezone
from telethon import events
from telethon.tl.types import Chat, Message, PeerChat, MessageService, MessageActionChatAddUser, UpdateNewMessage, User, PeerUser
from telegram_cache import connect_write
from telegram_events import Memberships, reconcile_memberships, sync_chat, is_member_group, handle_membership


def group(id=1):
    return Chat(id=id, title='Audit', photo=None, participants_count=2,
                date=datetime.now(timezone.utc), version=1)


class Client:
    def __init__(self, groups):
        self.groups = groups
        self.fail = False

    async def iter_dialogs(self):
        for entity in self.groups:
            yield SimpleNamespace(entity=entity)
        if self.fail:
            raise RuntimeError('partial scan')


class MembershipTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = connect_write(self.tmp.name + '/cache.sqlite')
        self.memberships = Memberships(self.db)
        self.client = Client([group()])
        self.ids = []

    async def asyncTearDown(self):
        self.db.close()
        self.tmp.cleanup()

    async def joined(self, entity):
        event = self.memberships.join(-entity.id)
        if event:
            self.ids.append(event)
            self.memberships.delivered(-entity.id)

    async def scan(self):
        await reconcile_memberships(self.db, self.client, self.memberships, self.joined)

    async def test_baseline_restart_offline_join_and_duplicate_notifications(self):
        await self.scan()
        self.assertEqual(self.ids, [])
        self.memberships = Memberships(self.db)
        self.client.groups.append(group(2))
        await self.scan()
        await self.scan()
        await self.joined(group(2))
        self.assertEqual(len(self.ids), 1)
        self.memberships.leave(-2)
        await self.scan()
        self.assertEqual(len(set(self.ids)), 2)

    async def test_failed_scan_does_not_invent_departures_or_joins(self):
        await self.scan()
        self.client.groups = [group(2)]
        self.client.fail = True
        with self.assertRaises(RuntimeError):
            await self.scan()
        self.assertEqual(self.ids, [])
        self.assertIsNone(self.memberships.join(-1))

    async def test_failed_history_sync_keeps_same_pending_event_across_restart(self):
        await self.scan()
        first = self.memberships.join(-2)
        self.memberships = Memberships(self.db)
        self.assertEqual(first, self.memberships.join(-2))
        self.memberships.delivered(-2)
        self.assertIsNone(self.memberships.join(-2))

    async def test_join_sync_handles_empty_group_and_refreshes_previously_cached_history(self):
        entity = group()
        messages = []
        calls = []
        class HistoryClient:
            async def iter_messages(self, entity, **kwargs):
                calls.append(kwargs)
                for message in messages:
                    yield message
        client = HistoryClient()
        chat, trigger = await sync_chat(self.db, client, entity, None, [], None, refresh=True)
        self.assertIsNone(chat['last_message_id'])
        self.assertIsNone(trigger)
        m = Message(id=10, peer_id=PeerChat(1), date=datetime.now(timezone.utc), message='Earlier discussion')
        m.get_sender = AsyncMock(return_value=None)
        messages.append(m)
        await sync_chat(self.db, client, entity, None, [], None, refresh=True)
        m2 = Message(id=5, peer_id=PeerChat(1), date=datetime.now(timezone.utc), message='Newly visible older message')
        m2.get_sender = AsyncMock(return_value=None)
        messages.append(m2)
        await sync_chat(self.db, client, entity, None, [], None, refresh=True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 2)
        self.assertEqual(calls, [{'limit': 100}] * 3)

    async def test_real_service_update_for_self_emits_but_other_users_do_not(self):
        async def actor():
            return User(id=8, first_name="Alice")
        joined = AsyncMock()
        for added_user in [99, 42]:
            msg = MessageService(id=50, peer_id=PeerChat(1), from_id=PeerUser(8),
                                 date=datetime.now(timezone.utc), action=MessageActionChatAddUser(users=[added_user]))
            event = events.ChatAction.build(UpdateNewMessage(msg, pts=1, pts_count=1))
            event.get_chat = AsyncMock(return_value=group())
            event.get_added_by = actor
            await handle_membership(event, 42, self.memberships, joined)
        self.assertEqual(joined.await_count, 1)
        self.assertEqual(joined.await_args.args[1], "Alice")

    def test_only_current_groups_are_memberships(self):
        self.assertTrue(is_member_group(group()))
        left = group(); left.left = True
        self.assertFalse(is_member_group(left))
        kicked = group(); kicked.kicked = True
        self.assertFalse(is_member_group(kicked))
        self.assertFalse(is_member_group(SimpleNamespace(id=3)))


if __name__ == '__main__':
    unittest.main()
