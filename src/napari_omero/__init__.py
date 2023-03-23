try:
    from importlib.metadata import PackageNotFoundError, version
except ModuleNotFoundError:
    from importlib_metadata import PackageNotFoundError, version  # type: ignore

try:
    __version__ = version("napari-omero")
except PackageNotFoundError:
    __version__ = "not-installed"

from .widgets import OMEROWidget

__all__ = ["OMEROWidget"]
