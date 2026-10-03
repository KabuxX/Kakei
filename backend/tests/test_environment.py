import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class EnvironmentTests(unittest.TestCase):
    def test_repository_dotenv_is_loaded_independently_of_cwd_without_overriding_exports(self):
        from config.environment import load_environment
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'OPENAI_API_KEY': 'exported'}, clear=True):
            root = Path(directory)
            env = root / '.env'
            env.write_text('OPENAI_API_KEY=from-file\nMAPBOX_GEOCODING_ACCESS_TOKEN=geo-test\nKAKEI_AGENT_MODEL=test-model\n', encoding='utf-8')
            with patch('config.environment.ENV_PATH', env):
                load_environment()
            self.assertEqual(os.environ['OPENAI_API_KEY'], 'exported')
            self.assertEqual(os.environ['MAPBOX_GEOCODING_ACCESS_TOKEN'], 'geo-test')
            self.assertEqual(os.environ['KAKEI_AGENT_MODEL'], 'test-model')

    def test_server_loads_environment_before_creating_app(self):
        with patch('config.environment.load_environment') as load, patch('api.app.create_app') as create:
            create.side_effect = lambda *args, **kwargs: self.assertTrue(load.called)
            runpy.run_path(str(Path(__file__).resolve().parents[1] / 'server.py'))
            load.assert_called_once_with()
            create.assert_called_once()
