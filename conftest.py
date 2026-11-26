"""Point the user's home and the shared root at a throwaway folder before any module reads them."""

import atexit
import os
from pathlib import Path
import shutil
import tempfile

_SCRATCH_HOME = Path(tempfile.mkdtemp(prefix="cline-hooks-tests-"))
atexit.register(shutil.rmtree, _SCRATCH_HOME, ignore_errors=True)
os.environ["HOME"] = str(_SCRATCH_HOME)
os.environ["LLM_PROMPTS_HOME"] = str(_SCRATCH_HOME / "llm-prompts")
os.environ.pop("XDG_DATA_HOME", None)
os.environ.pop("CLINE_HOOKS_DATA_DIR", None)
