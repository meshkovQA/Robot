import sys
import os
from pathlib import Path

# автоматом подцепить yandex как пакет
pkg_root = Path(__file__).resolve()
if str(pkg_root) not in sys.path:
    sys.path.insert(0, str(pkg_root))
