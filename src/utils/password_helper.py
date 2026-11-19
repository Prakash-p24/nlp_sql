import sys
from src.auth import password_helper as _module
sys.modules[__name__] = _module
