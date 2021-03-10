import os
from functools import partial
from typing import Callable, List, Optional, Union

from napari_plugin_engine import napari_hook_implementation


from ..utils import parse_omero_url, get_proxy_obj
from .loaders import omero_proxy_reader, omero_url_reader


@napari_hook_implementation
def napari_get_reader(path: Union[str, List[str]]) -> Optional[Callable]:
    if isinstance(path, str):
        if parse_omero_url(path):
            return omero_url_reader
        else:
            proxy_obj = get_proxy_obj(os.path.basename(path))
            if proxy_obj:
                return partial(omero_proxy_reader, proxy_obj=proxy_obj)
    return None


@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    from ..widgets import OMEROWidget

    return (OMEROWidget, {'name': 'browser'})
