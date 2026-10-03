import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.store import Store, TrajectoryConflict

DRAFT = {'title': '給与', 'date': '2026-10-01T12:00', 'type': 'income', 'category': '収入', 'amount': 100}

class AgentStoreTests(unittest.TestCase):
    def setUp(self):
        from db.agent_store import AgentStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'db.sqlite3'
        self.domain = Store(self.path)
        self.domain.initialize([])
        self.store = AgentStore(self.path)
        self.thread = self.store.create_thread()

    def command(self):
        from agent.contracts import AgentCommand
        return AgentCommand('transaction.create', {}, DRAFT)

    def test_thread_messages_survive_reopen(self):
        from db.agent_store import AgentStore
        self.store.append_message(self.thread['id'], 'client-1', 'user', '給与を追加')
        reopened = AgentStore(self.path).get_thread(self.thread['id'])
        self.assertEqual(reopened['messages'][0]['text'], '給与を追加')
        self.assertEqual(self.store.list_threads()[0]['id'], self.thread['id'])

    def test_message_retry_uses_client_id(self):
        first = self.store.append_message(self.thread['id'], 'client-1', 'user', '給与を追加')
        second = self.store.append_message(self.thread['id'], 'client-1', 'user', '給与を追加')
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(self.store.get_thread(self.thread['id'])['messages']), 1)
        with self.assertRaises(TrajectoryConflict):
            self.store.append_message(self.thread['id'], 'client-1', 'user', '別の指示')

    def test_revise_increments_revision(self):
        proposal = self.store.create_proposal(self.thread['id'], [self.command()], {})
        revised = self.store.revise_proposal(proposal['id'], 1, [self.command()])
        self.assertEqual(revised['revision'], 2)
        with self.assertRaises(TrajectoryConflict):
            self.store.revise_proposal(proposal['id'], 1, [self.command()])
        self.assertEqual(self.domain.list_transactions(), [])

    def test_expiry_and_rejection_remove_pending_only(self):
        proposal = self.store.create_proposal(self.thread['id'], [self.command()], {})
        self.assertAlmostEqual(proposal['expiresAt'] - proposal['createdAt'], 24 * 3600, delta=1)
        self.assertEqual(self.store.reject_proposal(proposal['id'])['status'], 'rejected')
        expiring = self.store.create_proposal(self.thread['id'], [self.command()], {})
        with self.domain._connection() as connection:
            connection.execute('UPDATE agent_proposals SET expires_at = ? WHERE id = ?', (time.time() - 1, expiring['id']))
        self.assertEqual(self.store.get_proposal(expiring['id'])['status'], 'expired')
        saved = self.domain.create_transaction(DRAFT)
        self.store.delete_thread(self.thread['id'])
        self.assertIsNone(self.store.get_thread(self.thread['id']))
        self.assertIsNotNone(self.domain.get_transaction(saved['id']))
