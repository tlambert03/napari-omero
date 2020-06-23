import functools
import logging
import os
import re
import time
from functools import partial

import dask.array as da
import numpy as np
import omero.gateway
from dask import delayed
from napari_plugin_engine import napari_hook_implementation
from omero.cli import ProxyStringType
from omero.gateway import BlitzGateway, PixelsWrapper
from omero.model.enums import (
    PixelsTypedouble,
    PixelsTypefloat,
    PixelsTypeint8,
    PixelsTypeint16,
    PixelsTypeint32,
    PixelsTypeuint8,
    PixelsTypeuint16,
    PixelsTypeuint32,
)
from omero.util.sessions import SessionsStore
from vispy.color import Colormap

from .widgets.gateway import QGateWay

logger = logging.getLogger(__name__)


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


STORE = SessionsStore()


def parse_omero_url(url):
    m = re.search(
        r"https?://(?P<host>[^/]+).*/webclient/\?show=(?P<type>[a-z]+)-(?P<id>[0-9]+)",
        url,
    )
    if m:
        return m.groupdict()


@timer
def get_gateway(path, host=None):
    gateway = QGateWay()
    if host:
        if host != gateway.host:
            gateway.close()
        gateway.host = host

    if gateway.isConnected():
        return gateway.conn
    else:
        conn = gateway._try_restore_session()
        if conn:
            return conn

    from .widgets.login import LoginForm

    form = LoginForm(gateway)
    gateway.connected.connect(form.accept)
    form.exec_()
    return form.gateway.conn


@timer
def _lookup(conn: BlitzGateway, proxy_obj):
    """Find object of type by ID."""
    conn.SERVICE_OPTS.setOmeroGroup("-1")
    type_ = proxy_obj.__class__.__name__.rstrip("I")
    obj = conn.getObject(type_, proxy_obj.id)
    if not obj:
        raise FileNotFoundError(f"No such {type_}: {proxy_obj.id}")
    return obj


def omero_url_reader(path):
    match = parse_omero_url(path)
    gateway = get_gateway(path, match.get("host"))
    if match.get("type").lower() == ("image"):
        wrapper = _lookup(gateway, ProxyStringType("Image")(f"Image:{match.get('id')}"))
        if wrapper:
            return load_omero_wrapper(wrapper)


@timer
def proxy_reader(path, proxy_obj=None):
    gateway = get_gateway(path)

    if proxy_obj.__class__.__name__.startswith("Image"):
        wrapper = _lookup(gateway, proxy_obj)
        if wrapper:
            return load_omero_wrapper(wrapper)


def load_omero_wrapper(wrapper):
    return [
        load_omero_channel(wrapper, channel, c)
        for c, channel in enumerate(wrapper.getChannels())
    ]


def load_omero_channel(image, channel, c_index):
    data = get_data_lazy(image, c=c_index)
    color = channel.getColor().getRGB()
    color = [r / 256 for r in color]
    cmap = Colormap([[0, 0, 0], color])
    scale = None

    if image.getSizeZ() > 1:
        size_x = image.getPixelSizeX()
        size_z = image.getPixelSizeZ()
        if size_x is not None and size_z is not None:
            if image.getSizeC() > 1:
                scale = [1, size_z / size_x, 1, 1]
            else:
                scale = [size_z / size_x, 1, 1]

    meta = {
        "blending": "additive",
        "colormap": ("from_omero", cmap),
        "scale": scale,
        "name": channel.getLabel(),
        "visible": channel.isActive(),
        "contrast_limits": [channel.getWindowStart(), channel.getWindowEnd()],
    }
    return (data, meta)


PIXEL_TYPES = {
    PixelsTypeint8: np.int8,
    PixelsTypeuint8: np.uint8,
    PixelsTypeint16: np.int16,
    PixelsTypeuint16: np.uint16,
    PixelsTypeint32: np.int32,
    PixelsTypeuint32: np.uint32,
    PixelsTypefloat: np.float32,
    PixelsTypedouble: np.float64,
}


@timer
def get_data_lazy(img, c=0):
    """Get n-dimensional dask array, with delayed reading from OMERO image."""
    sz = img.getSizeZ()
    st = img.getSizeT()
    plane_names = ["%s,%s,%s" % (z, c, t) for t in range(st) for z in range(sz)]
    pixels = img.getPrimaryPixels()

    @delayed
    @timer
    def get_plane(plane_name):
        z, c, t = [int(n) for n in plane_name.split(",")]
        p = pixels.getPlane(z, c, t)
        return p

    size_x = img.getSizeX()
    size_y = img.getSizeY()
    plane_shape = (size_y, size_x)
    dtype = PIXEL_TYPES.get(pixels.getPixelsType().value, None)

    lazy_arrays = [get_plane(pn) for pn in plane_names]
    dask_arrays = [
        da.from_delayed(delayed_reader, shape=plane_shape, dtype=dtype)
        for delayed_reader in lazy_arrays
    ]
    # Stack into one large dask.array
    if sz == 1 or st == 1:
        return da.stack(dask_arrays, axis=0)

    z_stacks = []
    for t in range(st):
        z_stacks.append(da.stack(dask_arrays[t * sz : (t + 1) * sz], axis=0))
    stack = da.stack(z_stacks, axis=0)
    return stack


PROXIES = (
    ProxyStringType("Image"),
    ProxyStringType("Dataset"),
    ProxyStringType("Project"),
)


def get_proxy_obj(path):
    for proxy_type in PROXIES:
        try:
            return proxy_type(path)
        except Exception:
            pass
    return None


def is_omero_url(path):
    return path.startswith("http") and "omero" in path and "?show" in path


@napari_hook_implementation
def napari_get_reader(path):
    if isinstance(path, str):
        if parse_omero_url(path):
            return omero_url_reader
        else:
            proxy_obj = get_proxy_obj(os.path.basename(path))
            if proxy_obj:
                return partial(proxy_reader, proxy_obj=proxy_obj)
    return None


class NonCachedPixelsWrapper(PixelsWrapper):
    """Extend gateway.PixelWrapper to override _prepareRawPixelsStore."""

    def _prepareRawPixelsStore(self):
        """
        Creates RawPixelsStore and sets the id etc

        This overrides the superclass behaviour to make sure that
        we don't re-use RawPixelStore in multiple processes since
        the Store may be closed in 1 process while still needed elsewhere.
        This is needed when napari requests may planes simultaneously,
        e.g. when switching to 3D view.
        """
        ps = self._conn.c.sf.createRawPixelsStore()
        ps.setPixelsId(self._obj.id.val, True, self._conn.SERVICE_OPTS)
        return ps


omero.gateway.PixelsWrapper = NonCachedPixelsWrapper
# Update the BlitzGateway to use our NonCachedPixelsWrapper
omero.gateway.refreshWrappers()
