"""Cerno — in-bank deployment of the Pulse friction-detection engine.

Import-time safety gate runs first. If any banned module is already
loaded in sys.modules, importing cerno raises SafetyViolation.
"""

from cerno.safety import assert_safe

assert_safe()

__version__ = "0.1.0"
