import sys, unittest
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.trajectory_intent import parse_creation_intent

class IntentTests(unittest.TestCase):
    def test_explicit_creation_dates_and_relative_days(self):
        for text,want in [('2026年10月1日の取引記録によって、軌跡を作って','2026-10-01'),('2026-10-01の軌跡を作成して','2026-10-01'),('昨日の軌跡を作って','2026-10-03')]:
            with self.subTest(text=text):
                self.assertEqual(parse_creation_intent(text,today=date(2026,10,4)).date,want)
    def test_consultation_quoted_instruction_and_multiple_dates_do_not_write(self):
        for text in ['軌跡を作る方法を教えて','「2026年10月1日の軌跡を作って」という指示の意味を説明して','2026年10月1日の軌跡を検索して','軌跡を作らないで']:
            self.assertIsNone(parse_creation_intent(text,today=date(2026,10,4)))
        for text in ['軌跡を作って','2026-10-01と2026-10-02の軌跡を作って','2026-02-30の軌跡を作って']:
            self.assertTrue(parse_creation_intent(text,today=date(2026,10,4)).needs_date)

    def test_past_creation_report_is_not_a_new_instruction(self):
        for text in ['2026-10-01の軌跡を作成した。内容を見せて','2026-10-01の軌跡は作成済みです','2026-10-01の軌跡を生成したが確認したい']:
            self.assertIsNone(parse_creation_intent(text,today=date(2026,10,4)))

    def test_quoted_tentative_and_prohibited_instructions_are_not_creation(self):
        for text in ['「2026年10月1日の軌跡を作って」は自然な日本語ですか？','2026年10月1日の軌跡を作っても大丈夫？','2026年10月1日の軌跡を作ってはいけません。検索だけして','"2026-10-01の軌跡を作って"と表示されています','2026年10月1日の軌跡を作成しないで','2026年10月1日の軌跡を追加しないで','2026年10月1日の軌跡を作っているのは誰ですか？','2026年10月1日の軌跡を作成してくださいという文章を翻訳して']:
            with self.subTest(text=text):self.assertIsNone(parse_creation_intent(text,today=date(2026,10,4)))

    def test_abbreviated_multiple_dates_and_ranges_need_one_date(self):
        for text in ['2026年10月1日と2日の軌跡を作って','2026年10月1日と10月2日の軌跡を作って','2026年10月1日から3日までの軌跡を作って','2026-10-01〜03の軌跡を作って']:
            with self.subTest(text=text):self.assertTrue(parse_creation_intent(text,today=date(2026,10,4)).needs_date)

    def test_creation_desire_and_addition_are_explicit_instructions(self):
        for text in ['2026年10月1日の軌跡を作成したい','2026年10月1日の軌跡を作成したいです','2026年10月1日の取引を軌跡に追加して']:
            with self.subTest(text=text):self.assertEqual(parse_creation_intent(text,today=date(2026,10,4)).date,'2026-10-01')
