
# robot/__init__.py

import sys
import os
from pathlib import Path

# Добавляем путь к third_party модулям
project_root = Path(__file__).parent.parent
third_party_path = project_root / "third_party" / "cloudapi_py"

if third_party_path.exists() and str(third_party_path) not in sys.path:
    sys.path.insert(0, str(third_party_path))
    print(f"Добавлен путь в PYTHONPATH: {third_party_path}")
