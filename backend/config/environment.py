"""Load local server settings without replacing explicitly exported variables."""
from dotenv import load_dotenv
from config.paths import BACKEND_DIR

ENV_PATH = BACKEND_DIR.parent / '.env'


def load_environment():
    load_dotenv(ENV_PATH, override=False)
