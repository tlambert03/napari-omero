from typing import List

import dask.array as da

from dask import delayed
from vispy.color import Colormap

from napari.types import LayerData
from omero.cli import ProxyStringType
from omero.gateway import BlitzGateway, ImageWrapper, ChannelWrapper
from omero.model import IObject

from ..utils import parse_omero_url, timer, lookup_obj, PIXEL_TYPES
from ..widgets import QGateWay


@timer
def get_gateway(path: str, host: str = None) -> BlitzGateway:
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


def omero_url_reader(path: str) -> List[LayerData]:
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


@timer
def omero_proxy_reader(
    path: str, proxy_obj: IObject = None
) -> List[LayerData]:
    gateway = get_gateway(path)

    if proxy_obj.__class__.__name__.startswith("Image"):
        wrapper = lookup_obj(gateway, proxy_obj)
        if isinstance(wrapper, ImageWrapper):
            return load_image_wrapper(wrapper)
    return []


def load_image_wrapper(image: ImageWrapper) -> List[LayerData]:
    return [
        load_omero_channel(image, channel, c)
        for c, channel in enumerate(image.getChannels())
    ]


def load_omero_channel(
    image: ImageWrapper, channel: ChannelWrapper, c_index: int
) -> LayerData:
    data = get_data_lazy(image, c_index=c_index)
    color = channel.getColor().getRGB()
    color = [r / 256 for r in color]
    cmap = Colormap([[0, 0, 0], color])
    scale = None

    # FIXME: still getting size mismatch sometimes  is there a getNDim()?
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
    # contrast limits range ... not accessible from plugin interface
    # win_min = channel.getWindowMin()
    # win_max = channel.getWindowMax()
    return (data, meta)


@timer
def get_data_lazy(image: ImageWrapper, c_index: int = 0) -> da.Array:
    """Get n-dimensional dask array, with delayed reading from OMERO image."""
    size_z = image.getSizeZ()
    size_t = image.getSizeT()
    size_x = image.getSizeX()
    size_y = image.getSizeY()
    pixels = image.getPrimaryPixels()

    @delayed
    @timer
    def get_plane(plane_name):
        z, c, t = [int(n) for n in plane_name.split(",")]
        p = pixels.getPlane(z, c, t)
        return p

    dtype = PIXEL_TYPES.get(pixels.getPixelsType().value, None)

    plane_names = [
        f"{z},{c_index},{t}" for t in range(size_t) for z in range(size_z)
    ]
    lazy_arrays = [get_plane(pn) for pn in plane_names]
    dask_arrays = [
        da.from_delayed(delayed_reader, shape=(size_y, size_x), dtype=dtype)
        for delayed_reader in lazy_arrays
    ]
    # Stack into one large dask.array
    if size_z == 1 or size_t == 1:
        return da.stack(dask_arrays, axis=0)

    z_stacks = []
    for t in range(size_t):
        z_stacks.append(
            da.stack(dask_arrays[t * size_z : (t + 1) * size_z], axis=0)
        )
    stack = da.stack(z_stacks, axis=0)
    return stack
