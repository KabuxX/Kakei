import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.google_places import GoogleCandidate
from google_places_fixtures import place
from services.receipt_location_matching import match_receipt_places, receipt_query_variants


def receipt(**values):
    return {
        **dict(merchant='セブン-イレブン', branch='千代田店', locality=None, merchantAddress=None), **values}


def candidate(**values):
    return GoogleCandidate.from_payload(place(**values))


class ReceiptMatchingTests(unittest.TestCase):
    def test_exact_branch_unique(self):
        self.assertEqual(match_receipt_places(receipt(), [candidate()]), {
            'status': 'resolved', 'placeIds': ['fixture-chiyoda'],
            'selectedPlaceId': 'fixture-chiyoda', 'method': 'google_unique', 'reason': None})

    def test_brand_only_never_auto_resolves(self):
        for values in ({'branch': None}, {'branch': None, 'merchantAddress': '東京都千代田区二番町8-8'}):
            result = match_receipt_places(receipt(**values), [candidate()])
            self.assertEqual(result['status'], 'needs_selection')
            self.assertIsNone(result['selectedPlaceId'])
            self.assertEqual(result['reason'], 'insufficient_identity')

    def test_same_building_different_branch(self):
        result = match_receipt_places(receipt(), [candidate(identifier='other', name='セブン-イレブン 麹町店')])
        self.assertEqual(result['placeIds'], [])
        self.assertEqual(result['reason'], 'identity_mismatch')

    def test_missing_address_or_political_place_excluded(self):
        political = place(identifier='political'); political['types'] = ['locality', 'political']
        for row in (candidate(address=''), GoogleCandidate.from_payload(political)):
            self.assertEqual(match_receipt_places(receipt(), [row])['placeIds'], [])

    def test_without_coordinates_can_resolve(self):
        self.assertEqual(match_receipt_places(receipt(), [candidate(coordinates=None)])['status'], 'resolved')

    def test_duplicate_ids_and_normalized_query(self):
        value = receipt(merchant=' ｾﾌﾞﾝ‐ｲﾚﾌﾞﾝ ', branch=' 千代田店 ', locality=' 東京都千代田区 ')
        self.assertEqual(receipt_query_variants(value), ['セブン-イレブン 千代田店 東京都千代田区'])
        self.assertEqual(match_receipt_places(value, [candidate(), candidate()])['status'], 'resolved')
        self.assertEqual(len(match_receipt_places(receipt(branch=None), [candidate(identifier=str(i)) for i in range(12)])['placeIds']), 10)

    def test_address_and_locality_conflicts_excluded(self):
        for value in (receipt(merchantAddress='東京都千代田区二番町9-9'), receipt(locality='東京都中央区'),
                      receipt(merchantAddress='〒999-9999 東京都千代田区二番町8-8')):
            row = candidate(address='〒102-0084 東京都千代田区二番町8-8')
            self.assertEqual(match_receipt_places(value, [row])['placeIds'], [])

    def test_ambiguous_missing_input_and_empty_results(self):
        self.assertEqual(match_receipt_places(receipt(), [candidate(identifier='a'), candidate(identifier='b')])['reason'], 'ambiguous')
        self.assertEqual(match_receipt_places(receipt(merchant='', branch=None), [candidate()])['status'], 'needs_input')
        self.assertEqual(match_receipt_places(receipt(), [])['reason'], 'not_found')

    def test_branch_in_merchant_and_normalized_address(self):
        value = receipt(merchant='セブン-イレブン 千代田店', branch=None, merchantAddress='東京都千代田区二番町８−８')
        self.assertEqual(match_receipt_places(value, [candidate()])['status'], 'resolved')
        self.assertLessEqual(len(receipt_query_variants(value)), 2)

    def test_unknown_chain_prefix_requires_selection(self):
        value = receipt(merchant='Example Coffee', branch=None)
        result = match_receipt_places(value, [candidate(name='Example Coffee Central Branch')])
        self.assertEqual(result['status'], 'needs_selection')
        self.assertIsNone(result['selectedPlaceId'])
        self.assertEqual(result['placeIds'], ['fixture-chiyoda'])

    def test_unknown_bare_name_requires_specificity_evidence(self):
        row = candidate(name='Example Coffee')
        self.assertEqual(match_receipt_places(receipt(merchant='Example Coffee', branch=None), [row])['status'], 'needs_selection')
        self.assertEqual(match_receipt_places(receipt(merchant='Example Coffee', branch=None, locality='東京都千代田区'), [row])['status'], 'resolved')

    def test_bare_brand_variation_is_not_branch_evidence(self):
        value = receipt(merchant='スターバックス コーヒー', branch=None)
        row = candidate(name='スターバックス コーヒー')
        result = match_receipt_places(value, [row])
        self.assertEqual(result['status'], 'needs_selection')
        self.assertIsNone(result['selectedPlaceId'])
        self.assertEqual(result['reason'], 'insufficient_identity')
