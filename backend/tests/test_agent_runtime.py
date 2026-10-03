import asyncio, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.runtime import AgentRunner, TurnLimit
from db.store import Store
from test_agent_changes import DRAFT
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from pydantic import PrivateAttr

class ScriptModel(BaseChatModel):
    replies: list
    _index: int = PrivateAttr(default=0)
    _names: list = PrivateAttr(default_factory=list)
    @property
    def _llm_type(self): return 'script'
    def bind_tools(self, tools, **kwargs):
        self._names = [tool.name for tool in tools]
        return self
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        message = self.replies[self._index]; self._index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name)/'db'); self.store.initialize([])

    async def test_runtime_registers_three_tools_and_stages_edits(self):
        model = ScriptModel(replies=[AIMessage(content='', tool_calls=[{'name':'edit_transaction','args':{'operation':'create','data':DRAFT},'id':'1','type':'tool_call'}]), AIMessage(content='確認してください')])
        result = await AgentRunner(self.store, model=model).run_turn('thread', [{'role':'user','text':'給与を記録'}])
        self.assertEqual(set(model._names), {'read_sql','edit_transaction','edit_trajectory','trajectory_context','search_place'})
        self.assertEqual(result['commands'][0]['data'], DRAFT)
        self.assertEqual(self.store.list_transactions(), [])

    async def test_tool_and_time_limits(self):
        calls = [{'name':'read_sql','args':{'sql':'SELECT 1'},'id':str(i),'type':'tool_call'} for i in range(9)]
        model = ScriptModel(replies=[AIMessage(content='', tool_calls=calls), AIMessage(content='done')])
        with self.assertRaises(TurnLimit):
            await AgentRunner(self.store, model=model).run_turn('t', [{'role':'user','text':'test'}])
        async def slow(*args, **kwargs): await asyncio.sleep(1)
        with patch('agent.runtime.TURN_SECONDS', 0.01), patch('langgraph.graph.state.CompiledStateGraph.ainvoke', side_effect=slow):
            with self.assertRaises(TimeoutError):
                await AgentRunner(self.store, model=ScriptModel(replies=[])).run_turn('t', [{'role':'user','text':'test'}])
