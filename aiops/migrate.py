import os

from alembic import command
from alembic.config import Config

_HERE = os.path.dirname(os.path.abspath(__file__))


def run_migrations() -> None:
    cfg = Config(os.path.join(_HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_HERE, "alembic"))
    command.upgrade(cfg, "head")
