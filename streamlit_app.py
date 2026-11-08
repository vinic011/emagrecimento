"""Community Cloud entrypoint: persistent PostgreSQL is mandatory."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__',
               init_globals={'REQUIRE_REMOTE_DB': True})
