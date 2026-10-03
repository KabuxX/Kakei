import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.contracts import AgentCommand
from db.agent_store import AgentStore
from db.store import Store, TrajectoryConflict
from services.validation import ValidationError

DRAFT = {'title': '給与', 'date': '2026-10-01T12:00', 'type': 'income', 'category': '収入', 'amount': 100}

class AgentChangesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'db.sqlite3'
        self.store = Store(self.path)
        self.store.initialize([])
        self.agent = AgentStore(self.path)
        self.thread = self.agent.create_thread()['id']

    def proposal(self, commands=None):
        return self.agent.create_proposal(self.thread, commands or [AgentCommand('transaction.create', {}, DRAFT)], {})

    def test_unapproved_proposal_never_writes(self):
        proposal = self.proposal()
        self.assertEqual(self.store.list_transactions(), [])
        self.assertEqual(proposal['before'], [None])
        self.assertEqual(proposal['after'][0]['amount'], 100)
        self.agent.reject_proposal(proposal['id'])
        with self.assertRaises(TrajectoryConflict):
            self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(self.store.list_transactions(), [])

    def test_transaction_and_day_apply_atomically(self):
        proposal = self.proposal([AgentCommand('transaction.create', {}, DRAFT),
            AgentCommand('trajectory.create', {'kind': 'day', 'date': '2026-10-01'}, {'events': [], 'legs': []})])
        self.assertIsNone(self.store.get_trajectory_day('2026-10-01'))
        self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(len(self.store.list_transactions()), 1)
        self.assertEqual(self.store.get_trajectory_day('2026-10-01')['days'][0]['events'], [])
        self.assertEqual(self.agent.get_proposal(proposal['id'])['status'], 'applied')

    def test_stale_record_or_revision_conflicts(self):
        record = self.store.create_transaction(DRAFT)
        commands = [AgentCommand('transaction.update', {'id': record['id']}, {**DRAFT, 'amount': 200})]
        proposal = self.proposal(commands)
        self.store.update_transaction(record['id'], {**DRAFT, 'amount': 300})
        with self.assertRaises(TrajectoryConflict):
            self.store.apply_agent_proposal(proposal['id'], 1)
        revised = self.agent.revise_proposal(proposal['id'], 1, commands)
        self.assertEqual(revised['before'][0]['amount'], 300)
        with self.assertRaises(TrajectoryConflict):
            self.store.apply_agent_proposal(proposal['id'], 1)
        self.store.apply_agent_proposal(proposal['id'], 2)
        self.assertEqual(self.store.get_transaction(record['id'])['amount'], 200)

    def test_approval_retry_returns_saved_result(self):
        proposal = self.proposal()
        first = self.store.apply_agent_proposal(proposal['id'], 1)
        second = Store(self.path).apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.list_transactions()), 1)
        with self.assertRaises(TrajectoryConflict):
            self.store.apply_agent_proposal(proposal['id'], 2)

    def test_bad_second_command_rolls_back_first(self):
        proposal = self.proposal([AgentCommand('transaction.create', {}, DRAFT), AgentCommand('transaction.create', {}, DRAFT)])
        insert = Store._insert
        calls = []
        def failing_insert(connection, record):
            insert(connection, record)
            calls.append(record['id'])
            if len(calls) == 2:
                raise ValidationError('amount', 'forced failure')
        with patch.object(Store, '_insert', side_effect=failing_insert), self.assertRaises(ValidationError):
            self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(Store(self.path).list_transactions(), [])
        self.assertEqual(self.agent.get_proposal(proposal['id'])['status'], 'pending')
        self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(len(self.store.list_transactions()), 2)
