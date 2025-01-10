import os
from functools import partial
from typing import Callable, Optional, Union

from napari_omero.utils import get_proxy_obj, parse_omero_url

from .loaders import omero_proxy_reader, omero_url_reader


def napari_get_reader(path: Union[str, list[str]]) -> Optional[Callable]:
    if isinstance(path, str):
        if parse_omero_url(path):
            return omero_url_reader
        proxy_obj = get_proxy_obj(os.path.basename(path))
        if proxy_obj:
            return partial(omero_proxy_reader, proxy_obj=proxy_obj)
    return None
