import copy,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.place_matching import EvidenceResolver, short_query, match_candidates, resolve_region
from db.agent_search_store import AgentSearchStore
from services.validation import ValidationError
from agent_search_fixtures import active_turn, SEARCH, FUKUOKA, SHOP, STATION

class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store,self.agent,self.ctx=active_turn(Path(self.tmp.name)/'db')
        self.messages=[{'id':'u','role':'user','text':'ドトールコーヒーショップ 西鉄福岡駅店 福岡市 天神'}]
        self.resolver=EvidenceResolver(self.store,AgentSearchStore(self.store.db_path),self.ctx['thread_id'],self.messages)

    def test_fukuoka_evidence_and_short_query(self):
        request={**SEARCH,'query':'ドトールコーヒーショップ 西鉄福岡駅店'}
        result=self.resolver.resolve(request)
        self.assertEqual(result['category'],'catering.cafe')
        region=resolve_region([STATION],request)['region']
        self.assertEqual(region['city'],'福岡市')
        self.assertEqual(short_query(request,region),'ドトール 福岡市 天神')
        matched=match_candidates([SHOP],request,region)
        self.assertFalse(matched['exact_match'])
        self.assertIn('branch_unconfirmed',matched['candidates'][0]['matchReasons'])

    def test_distinct_branches_never_collapse(self):
        rows=[SHOP,{**SHOP,'id':'b','providerId':'b','coordinates':[130.399,33.589]}]
        self.assertEqual(len(match_candidates(rows,SEARCH,FUKUOKA)['candidates']),2)
        rows.append({**SHOP,'id':'dup','name':'ドトール'})
        self.assertEqual(len(match_candidates(rows,SEARCH,FUKUOKA)['candidates']),2)
        bad={**SHOP,'name':'ドトールコーヒーショップ 博多駅店','confidence':1}
        self.assertEqual(match_candidates([bad],SEARCH,FUKUOKA)['candidates'],[])
        tokyo={**SHOP,'city':'東京都','address':'東京都','coordinates':[139.7,35.7]}
        self.assertEqual(match_candidates([tokyo],SEARCH,FUKUOKA)['candidates'],[])

    def test_current_region_conflict_is_explicit(self):
        self.messages.extend([{'id':'old','role':'user','text':'東京'},{'id':'new','role':'user','text':'今回は福岡市'}])
        request={**SEARCH,'locality':'福岡市','evidence':[{'field':'locality','source':'user_message','source_id':'old','value':'東京'},{'field':'locality','source':'user_message','source_id':'new','value':'福岡市'}]}
        self.assertEqual(self.resolver.resolve(request)['clarification']['status'],'needs_clarification')

    def test_missing_address_does_not_become_exact(self):
        row={**SHOP,'name':SEARCH['query'],'address':'','city':'','district':'','country_code':''}
        found=match_candidates([row],SEARCH,None)
        self.assertFalse(found['exact_match'])
        self.assertIn('region_unconfirmed',found['candidates'][0]['matchReasons'])

    def test_validation_and_ambiguous_region(self):
        for override in ({'query':''},{'query':'a'*201},{'country_code':'zz'},{'locality':'東京','evidence':[{'field':'locality','source':'user_message','source_id':'u','value':'東京'}]}):
            with self.assertRaises(ValidationError): self.resolver.resolve({**SEARCH,**override})
        other={**STATION,'id':'other','providerId':'other','city':'別市'}
        self.assertEqual(resolve_region([STATION,other],SEARCH)['clarification']['status'],'needs_clarification')
        forged={**SHOP,'coordinates':[float('nan'),33]}
        self.assertEqual(match_candidates([forged],SEARCH,FUKUOKA)['candidates'],[])

    def test_foreign_place_and_scoped_evidence(self):
        request={'query':'Cafe London','place_id':'ab','brand':'Cafe'}
        row={**SHOP,'name':'Cafe London','address':'London UK','city':'London','country_code':'gb','coordinates':[-.1,51.5]}
        self.assertEqual(len(match_candidates([row],request,{'kind':'point','city':'London','country_code':'gb','coordinates':[-.1,51.5]})['candidates']),1)
        with self.assertRaises(ValidationError):
            self.resolver.resolve({**SEARCH,'locality':'福岡市','evidence':[{'field':'locality','source':'user_message','source_id':'missing','value':'福岡市'}]})
