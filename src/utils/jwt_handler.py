import sys
from src.auth import jwt_handler as _module
sys.modules[__name__] = _module
