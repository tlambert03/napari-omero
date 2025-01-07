from typing import Optional

import dask.array as da
from dask.delayed import delayed
from napari.types import LayerData
from vispy.color import Colormap

from napari_omero.utils import PIXEL_TYPES, lookup_obj, parse_omero_url, timer
from napari_omero.widgets import QGateWay
from omero.cli import ProxyStringType
from omero.gateway import BlitzGateway, ImageWrapper
from omero.model import IObject


# @timer
def get_gateway(path: str, host: Optional[str] = None) -> BlitzGateway:
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

    from napari_omero.widgets.login import LoginForm

    form = LoginForm(gateway)
    gateway.connected.connect(form.accept)
    form.exec_()
    return form.gateway.conn


def omero_url_reader(path: str) -> list[LayerData]:
    match = parse_omero_url(path)
    if not match:
        return []
    gateway = get_gateway(path, match.get("host"))
    if match.get("type", "").lower() == "image":
        wrapper = lookup_obj(
            gateway, ProxyStringType("Image")(f"Image:{match.get('id')}")
        )
        if isinstance(wrapper, ImageWrapper):
            return load_image_wrapper(wrapper)
    return []


# @timer
def omero_proxy_reader(
    path: str, proxy_obj: Optional[IObject] = None
) -> list[LayerData]:
    gateway = get_gateway(path)

    if proxy_obj.__class__.__name__.startswith("Image"):
        wrapper = lookup_obj(gateway, proxy_obj)
        if isinstance(wrapper, ImageWrapper):
            return load_image_wrapper(wrapper)
    return []


def load_image_wrapper(image: ImageWrapper) -> list[LayerData]:
    data = get_data_lazy(image)
    meta = get_omero_metadata(image)
    # contrast limits range ... not accessible from plugin interface
    # win_min = channel.getWindowMin()
    # win_max = channel.getWindowMax()
    return [(data, meta)]


def get_omero_metadata(image: ImageWrapper) -> dict:
    """Get metadata from OMERO as a Dict to pass to napari."""
    channels = image.getChannels()

    colors = []
    for ch in channels:
        # use current rendering settings from OMERO
        color = ch.getColor().getRGB()
        color = [r / 256 for r in color]
        colors.append(Colormap([[0, 0, 0], color]))

    contrast_limits = [[ch.getWindowStart(), ch.getWindowEnd()] for ch in channels]

    visibles = [ch.isActive() for ch in channels]
    names = [ch.getLabel() for ch in channels]

    scale = None
    # Setting z-scale causes issues with Z-slider.
    # See https://github.com/tlambert03/napari-omero/pull/15
    # if image.getSizeZ() > 1:
    #     size_x = image.getPixelSizeX()
    #     size_z = image.getPixelSizeZ()
    #     if size_x is not None and size_z is not None:
    #         scale = [1, size_z / size_x, 1, 1]

    return {
        "channel_axis": 1,
        "colormap": colors,
        "contrast_limits": contrast_limits,
        "name": names,
        "visible": visibles,
        "scale": scale,
    }


# @timer
def get_data_lazy(image: ImageWrapper) -> da.Array:
    """Get 5D dask array, with delayed reading from OMERO image."""
    nt, nc, nz, ny, nx = (getattr(image, f"getSize{x}")() for x in "TCZYX")
    pixels = image.getPrimaryPixels()
    dtype = PIXEL_TYPES.get(pixels.getPixelsType().value, None)
    get_plane = delayed(timer(lambda idx: pixels.getPlane(*idx)))

    def get_lazy_plane(zct: tuple[int, ...]):
        return da.from_delayed(get_plane(zct), shape=(ny, nx), dtype=dtype)

    # 5D stack: TCZXY
    t_stacks = []
    for t in range(nt):
        c_stacks = []
        for c in range(nc):
            z_stack = []
            for z in range(nz):
                z_stack.append(get_lazy_plane((z, c, t)))
            c_stacks.append(da.stack(z_stack))
        t_stacks.append(da.stack(c_stacks))
    return da.stack(t_stacks)
