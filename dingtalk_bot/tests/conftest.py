"""让测试能 import 上级目录的模块（prompt / ai_client / stream_client 等）。"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
