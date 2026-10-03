"""Receipt arithmetic: literal expectations independently calculated from the sample."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.receipt import ReceiptCandidate, receipt_review

SAMPLE = {
    'merchant':'セブンイレブン 千代田店','date':'2026-10-01','time':'08:45',
    'currency':'JPY','payment_method':'e_money','total':1161,'paid_total':1139,'discount':22,
    'items':[
        {'name':'おにぎり','amount':130,'tax_group':'food'},
        {'name':'コーラ','amount':140,'tax_group':'food'},
        {'name':'ミニネイル','amount':300,'tax_group':'cosmetics'},
        {'name':'たばこ','amount':490,'tax_group':'included'},
        {'name':'切手','amount':50,'tax_group':'exempt'},
    ],
    'tax_groups':[
        {'id':'food','basis':'exclusive','rate':8,'subtotal':270,'tax':21},
        {'id':'cosmetics','basis':'exclusive','rate':10,'subtotal':300,'tax':30},
        {'id':'included','basis':'inclusive','rate':10,'subtotal':490,'tax':44},
        {'id':'exempt','basis':'exempt','rate':0,'subtotal':50,'tax':0},
    ],
}

class AmountTests(unittest.TestCase):
    def review(self, data):
        try:
            candidate=ReceiptCandidate.model_validate(data)
        except ValueError as exc:
            self.fail(f"Receipt extraction must accept printed tax evidence: {exc}")
        return receipt_review(candidate, [], 'receipt')

    def test_mixed_tax_then_reduction_conserves_printed_totals_and_raw_values(self):
        review=self.review(SAMPLE)
        self.assertFalse(review['itemMismatch'])
        calc=review['calculation']
        self.assertEqual(calc['issues'], [])
        self.assertEqual([r['addedTax'] for r in calc['rows']], [10,11,30,0,0])
        self.assertEqual([r['gross'] for r in calc['rows']], [140,151,330,490,50])
        self.assertEqual([r['discount'] for r in calc['rows']], [3,3,6,9,1])
        self.assertEqual([i['amount'] for i in review['preparedDraft']['items']], [137,148,324,481,49])
        self.assertEqual(review['preparedDraft']['amount'], 1139)
        self.assertEqual(review['candidate']['items'][0]['amount'], 130)

    def test_equal_remainders_use_printed_order_without_float_rounding(self):
        data={'total':21,'currency':'JPY','items':[{'name':'A','amount':10,'tax_group':'g'},{'name':'B','amount':10,'tax_group':'g'}],
              'tax_groups':[{'id':'g','basis':'exclusive','rate':8,'subtotal':20,'tax':1}]}
        self.assertEqual([i['amount'] for i in self.review(data)['preparedDraft']['items']], [11,10])

    def test_ambiguous_or_inconsistent_evidence_never_produces_prepared_draft(self):
        mutations=[lambda d:d['tax_groups'][0].update(subtotal=271),
                   lambda d:d['tax_groups'][0].update(tax=None),
                   lambda d:d['tax_groups'][0].update(tax=50),
                   lambda d:d['items'][0].update(tax_group=None),
                   lambda d:d.update(total=1162), lambda d:d.update(paid_total=1138),
                   lambda d:d.update(discount=None), lambda d:d.update(currency='USD'),
                   lambda d:d['tax_groups'].append(dict(d['tax_groups'][0])),
                   lambda d:d.update(paid_total=0,discount=1161)]
        for mutate in mutations:
            data=copy.deepcopy(SAMPLE);mutate(data)
            with self.subTest(data=data):
                review=self.review(data)
                self.assertIsNone(review['preparedDraft'])
                self.assertTrue(review['calculation']['issues'])

    def test_included_tax_is_not_added_again(self):
        data={'total':110,'currency':'JPY','items':[{'name':'A','amount':110,'tax_group':'g'}],
              'tax_groups':[{'id':'g','basis':'inclusive','rate':10,'subtotal':110,'tax':10}]}
        self.assertEqual(self.review(data)['preparedDraft']['items'],[{'name':'A','amount':110}])
