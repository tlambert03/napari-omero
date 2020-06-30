import functools
import logging
import re
import time
from typing import Dict, Optional

import numpy as np
from omero.cli import ProxyStringType
from omero.gateway import BlitzGateway, BlitzObjectWrapper
from omero.model import IObject
from omero.model import enums as omero_enums

logger = logging.getLogger(__name__)

PIXEL_TYPES = {
    omero_enums.PixelsTypeint8: np.int8,
    omero_enums.PixelsTypeuint8: np.uint8,
    omero_enums.PixelsTypeint16: np.int16,
    omero_enums.PixelsTypeuint16: np.uint16,
    omero_enums.PixelsTypeint32: np.int32,
    omero_enums.PixelsTypeuint32: np.uint32,
    omero_enums.PixelsTypefloat: np.float32,
    omero_enums.PixelsTypedouble: np.float64,
}

PROXIES = (
    ProxyStringType("Image"),
    ProxyStringType("Dataset"),
    ProxyStringType("Project"),
)


def timer(func):
    """Print the runtime of the decorated function"""

    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        start_time = time.perf_counter()  # 1
        value = func(*args, **kwargs)
        end_time = time.perf_counter()  # 2
        run_time = end_time - start_time  # 3
        logger.debug(f"Finished {func.__name__!r} in {run_time:.4f} secs")
        return value

    return wrapper_timer


@timer
def lookup_obj(conn: BlitzGateway, iobj: IObject) -> BlitzObjectWrapper:
    """Find object of type by ID."""
    conn.SERVICE_OPTS.setOmeroGroup("-1")
    type_ = iobj.__class__.__name__.rstrip("I")
    obj = conn.getObject(type_, iobj.id)
    if not obj:
        raise NameError(f"No such {type_}: {iobj.id}")

    return obj


omero_url_pattern = re.compile(
    r"https?://(?P<host>[^/]+).*/webclient"
    r"/\?show=(?P<type>[a-z]+)-(?P<id>[0-9]+)"
)

omero_object_pattern = re.compile(
    r"(?P<type>(Image|Dataset|Project)):(?P<id>[0-9]+)"
)


def parse_omero_url(url: str) -> Optional[Dict[str, str]]:
    match = omero_url_pattern.search(url)
    return match.groupdict() if match else None


def get_proxy_obj(path: str) -> Optional[IObject]:
    """If path ends with e.g. Image:ID return proxy obj"""
    match = omero_object_pattern.search(path)
    if match is None:
        return None
    for proxy_type in PROXIES:
        try:
            return proxy_type(path)
        except Exception:
            pass
    return None


def obj_to_proxy_string(iobj: IObject) -> str:
    type_ = iobj.__class__.__name__.rstrip("I")
    return f"{type_}:{iobj.id.val}"
