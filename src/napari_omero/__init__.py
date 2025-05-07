from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("napari-omero")
except PackageNotFoundError:
    __version__ = "not-installed"

from .widgets import OMEROWidget

__all__ = ["OMEROWidget"]
