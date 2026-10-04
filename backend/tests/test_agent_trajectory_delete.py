"""Deletion review uses disposable data and the real approval transaction."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.contracts import command_dicts
from agent.runtime import AgentRunner
from db.agent_store import AgentStore
from db.store import Store, TrajectoryConflict, TrajectoryNotFound
from services.validation import ValidationError
from test_agent_runtime import ScriptModel
from test_trajectory_evidence import PLACE
from langchain_core.messages import AIMessage

DAY = '2027-01-04'


def deletion(kind, **identity):
    return {'kind': 'trajectory.delete', 'identity': {'kind': kind, 'date': DAY, **identity}, 'data': {}}


class TrajectoryDeletionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'db'
        self.store = Store(self.path)
        self.store.initialize([])
        self.tx = self.store.create_transaction({'title': '給与', 'date': DAY+'T09:00', 'type': 'income', 'category': '収入', 'amount': 100})
        self.day = {'date': DAY, 'events': [
            {'id': name, 'placeId': 'p', 'time': f'{hour:02}:00', 'timeEvidence': 'exact', 'timeEvidenceNote': None}
            for name, hour in zip('abcd', range(9, 13))], 'legs': [
            {'fromEventId': a, 'toEventId': b, 'modeEvidence': 'inferred', 'modeEvidenceNote': '概算'}
            for a, b in zip('abc', 'bcd')]}
        self.day['events'][0]['transactionId'] = self.tx['id']
        self.other = {'date': '2027-01-05', 'events': [{'id': 'other', 'placeId': 'p', 'time': '09:00', 'timeEvidence': 'exact', 'timeEvidenceNote': None}], 'legs': []}
        self.store.sync_trajectory({'places': {'p': PLACE}, 'days': [self.day, self.other]})
        self.agent = AgentStore(self.path)
        self.thread = self.agent.create_thread()['id']

    def saved(self):
        return self.store.get_trajectory_day(DAY)['days'][0]

    async def test_day_delete_requires_approval_and_survives_restart_and_retry(self):
        proposal = self.agent.create_proposal(self.thread, [deletion('day')])
        self.assertEqual(self.saved(), self.day)
        self.assertEqual(proposal['before'], [self.day])
        self.assertEqual(proposal['after'], [None])
        self.assertEqual(proposal['metadata']['referenceLabels']['p'], PLACE['name'])
        result = self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(result['trajectoryDates'], [DAY])
        reopened = Store(self.path)
        self.assertIsNone(reopened.get_trajectory_day(DAY))
        self.assertEqual(reopened.apply_agent_proposal(proposal['id'], 1), result)
        self.assertEqual(reopened.get_trajectory_day('2027-01-05')['days'], [self.other])
        self.assertEqual(reopened.get_transaction(self.tx['id']), self.tx)
        with reopened._connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM trajectory_places').fetchone()[0], 1)

    async def test_event_delete_removes_only_connected_legs_without_reconnecting(self):
        proposal = self.agent.create_proposal(self.thread, [deletion('event', id='b')])
        expected = {**self.day, 'events': [e for e in self.day['events'] if e['id'] != 'b'], 'legs': self.day['legs'][2:]}
        self.assertEqual(proposal['before'], [self.day])
        self.assertEqual(proposal['after'], [expected])
        self.assertEqual(self.saved(), self.day)
        self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(self.saved(), expected)

    async def test_leg_delete_keeps_both_visits_and_other_legs(self):
        proposal = self.agent.create_proposal(self.thread, [deletion('leg', fromEventId='a', toEventId='b')])
        self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(self.saved(), {**self.day, 'legs': self.day['legs'][1:]})

    async def test_last_visit_delete_keeps_empty_day(self):
        command = {'kind': 'trajectory.delete', 'identity': {'kind': 'event', 'date': self.other['date'], 'id': 'other'}, 'data': {}}
        proposal = self.agent.create_proposal(self.thread, [command])
        self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(self.store.get_trajectory_day(self.other['date'])['days'], [{'date': self.other['date'], 'events': [], 'legs': []}])

    async def test_unknown_retained_visits_do_not_require_order_confirmation_for_delete(self):
        day = copy.deepcopy(self.day)
        for event in day['events']:
            event.update(time=None, timeEvidence='unknown')
        self.store.sync_trajectory({'places': {'p': PLACE}, 'days': [day]})
        proposal = self.agent.create_proposal(self.thread, [deletion('event', id='b')])
        self.assertFalse(proposal['metadata']['orderRequired'])
        self.store.apply_agent_proposal(proposal['id'], 1)

    async def test_changed_day_conflicts_and_revision_refreshes_the_preview(self):
        proposal = self.agent.create_proposal(self.thread, [deletion('day')])
        from services.trajectory_mutation import parse_trajectory_command
        command = parse_trajectory_command({'kind': 'leg', 'date': DAY, 'fromEventId': 'a', 'toEventId': 'b'}, 'DELETE')
        self.store.mutate_trajectory(command, 'delete')
        with self.assertRaises(TrajectoryConflict):
            self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(len(self.saved()['legs']), 2)
        revised = self.agent.revise_proposal(proposal['id'], 1, proposal['commands'])
        self.assertEqual(len(revised['before'][0]['legs']), 2)
        self.store.apply_agent_proposal(proposal['id'], revised['revision'])

    async def test_rejection_and_missing_target_do_not_write(self):
        proposal = self.agent.create_proposal(self.thread, [deletion('event', id='a')])
        self.agent.reject_proposal(proposal['id'], 1)
        with self.assertRaises(TrajectoryConflict):
            self.store.apply_agent_proposal(proposal['id'], 1)
        for command in [deletion('event', id='missing'), deletion('leg', fromEventId='a', toEventId='d')]:
            with self.subTest(command=command), self.assertRaises(TrajectoryNotFound):
                self.agent.create_proposal(self.thread, [command])
        self.assertEqual(self.saved(), self.day)

    async def test_changed_deleted_visit_place_requires_a_new_review(self):
        proposal = self.agent.create_proposal(self.thread, [deletion('day')])
        from services.trajectory_mutation import parse_trajectory_command
        self.store.mutate_trajectory(parse_trajectory_command({'kind': 'place', 'id': 'p', 'data': {**PLACE, 'name': '変更後の地点'}}, 'PUT'), 'update')
        with self.assertRaises(TrajectoryConflict):
            self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(self.saved(), self.day)

    async def test_save_failure_rolls_back_combined_transaction_and_delete(self):
        draft = {'title': '変更後', 'date': DAY+'T09:00', 'type': 'income', 'category': '収入', 'amount': 200}
        proposal = self.agent.create_proposal(self.thread, [{'kind': 'transaction.update', 'identity': {'id': self.tx['id']}, 'data': draft}, deletion('day')])
        with patch('services.agent_changes.replace_trajectory', side_effect=ValidationError('trajectory', 'save failed')):
            with self.assertRaises(ValidationError):
                self.store.apply_agent_proposal(proposal['id'], 1)
        self.assertEqual(self.store.get_transaction(self.tx['id']), self.tx)
        self.assertEqual(self.saved(), self.day)
        self.assertEqual(self.agent.get_proposal(proposal['id'])['status'], 'pending')

    async def test_unresolved_mixed_proposal_shows_real_deletion_diff(self):
        create = {'kind': 'trajectory.create', 'identity': {'kind': 'day', 'date': '2027-01-06'}, 'data': {'events': [{'id': 'future', 'placeId': 'unknown', 'time': '09:00', 'timeEvidence': 'exact'}], 'legs': []}}
        proposal = self.agent.create_proposal(self.thread, [deletion('day'), create], place_candidates=[{'placeId': 'unknown', 'query': '店', 'candidates': []}])
        self.assertIsNone(proposal['after'][0])
        self.assertEqual(proposal['before'][0], self.day)
        with self.assertRaises(TrajectoryConflict):
            self.store.apply_agent_proposal(proposal['id'], 1)

    async def test_agent_tool_can_stage_delete_without_data(self):
        model = ScriptModel(replies=[AIMessage(content='', tool_calls=[{'name': 'edit_trajectory', 'args': {'operation': 'delete', 'identity': {'kind': 'day', 'date': DAY}}, 'id': 'delete', 'type': 'tool_call'}]), AIMessage(content='削除対象を確認してください。')])
        result = await AgentRunner(self.store, model=model).run_turn(self.thread, [{'role': 'user', 'text': DAY+'の軌跡を削除'}])
        self.assertEqual(result['commands'], [deletion('day')])
        self.assertEqual(self.saved(), self.day)

    async def test_delete_rejects_data_and_shared_place_deletion(self):
        for command in [{**deletion('day'), 'data': {'events': []}}, {'kind': 'trajectory.delete', 'identity': {'kind': 'place', 'id': 'p'}, 'data': {}}]:
            with self.subTest(command=command), self.assertRaises(ValidationError):
                command_dicts([command])
