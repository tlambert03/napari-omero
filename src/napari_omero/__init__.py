try:
    from ._version import version as __version__
except ImportError:
    __version__ = "not-installed"

from .widgets import OMEROWidget

__all__ = ["OMEROWidget"]
