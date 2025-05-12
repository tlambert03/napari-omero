from contextlib import contextmanager
from math import ceil
from typing import Optional

import dask.array as da
import numpy as np
from dask.delayed import delayed
from napari.types import LayerData
from napari.utils.colormaps import ensure_colormap
from omero_marshal import get_encoder

from napari_omero.utils import PIXEL_TYPES, lookup_obj, parse_omero_url, timer
from napari_omero.widgets import QGateWay
from omero.cli import ProxyStringType
from omero.gateway import BlitzGateway, ImageWrapper
from omero.model import IObject


# @timer
def get_gateway(
    path: str, host: Optional[str] = None, force_reconnect: bool = False
) -> BlitzGateway:
    gateway = QGateWay()
    if host:
        if host != gateway.host:
            gateway.close()
        gateway.host = host

    if force_reconnect:
        gateway.conn = None

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


@contextmanager
def raw_pixels_store(image):
    pix = image._conn.c.sf.createRawPixelsStore()
    try:
        yield pix
    finally:
        pix.close()


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
        try:
            wrapper = lookup_obj(gateway, proxy_obj)
        except Exception:
            gateway = get_gateway(path, force_reconnect=True)
            if not gateway:
                return []
            wrapper = lookup_obj(gateway, proxy_obj)
        if isinstance(wrapper, ImageWrapper):
            return load_image_wrapper(wrapper)
    return []


def load_image_wrapper(image: ImageWrapper) -> list[LayerData]:
    meta = get_omero_metadata(image)
    # contrast limits range ... not accessible from plugin interface
    # win_min = channel.getWindowMin()
    # win_max = channel.getWindowMax()
    if image.requiresPixelsPyramid():
        data = get_pyramid_lazy(image)
    else:
        data = get_data_lazy(image)
    return [(data, meta, "image")]


BASIC_COLORMAPS = {
    "000000": "gray_r",
    "FFFFFF": "gray",
    "FF0000": "red",
    "00FF00": "green",
    "0000FF": "blue",
    "FF00FF": "magenta",
    "00FFFF": "cyan",
    "FFFF00": "yellow",
}


def get_omero_metadata(image: ImageWrapper) -> dict:
    """Get metadata from OMERO as a Dict to pass to napari."""
    channels = image.getChannels()

    colors = []
    for ch in channels:
        # use current rendering settings from OMERO
        color = ch.getColor()
        # ensure the basics work regardless of napari version
        if color.getHtml() in BASIC_COLORMAPS:
            colors.append(ensure_colormap(BASIC_COLORMAPS[color.getHtml()]))
        else:
            colors.append(ensure_colormap("#" + color.getHtml()))

    contrast_limits = [[ch.getWindowStart(), ch.getWindowEnd()] for ch in channels]

    visibles = [ch.isActive() for ch in channels]
    names = [f"{image.getId()}: {ch.getLabel()}" for ch in channels]

    size_x = image.getPixelSizeX() or 1
    size_y = image.getPixelSizeY() or 1
    size_z = image.getPixelSizeZ() or 1
    # data is TCZYX, but C is passed to channel_axis and split
    # so we only need scale to have 4 elements
    scale = [1, size_z, size_y, size_x]

    # get json metadata from omero
    img_obj = image._obj
    encoder = get_encoder(img_obj.__class__)
    metadata = {"omero": encoder.encode(img_obj)}

    return {
        "channel_axis": 1,
        "colormap": colors,
        "contrast_limits": contrast_limits,
        "name": names,
        "visible": visibles,
        "scale": scale,
        "metadata": metadata,
        "axis_labels": ("t", "z", "y", "x"),
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


def get_pyramid_lazy(image: ImageWrapper) -> list[da.Array]:
    """Get a pyramid of rgb dask arrays, loading tiles from OMERO."""
    size_z = image.getSizeZ()
    size_t = image.getSizeT()
    size_c = image.getSizeC()
    pixels = image.getPrimaryPixels()
    dtype = PIXEL_TYPES.get(pixels.getPixelsType().value, None)

    image._prepareRenderingEngine()
    tile_w, tile_h = image._re.getTileSize()

    def get_tile(tile_name):
        """tile_name is 'level,z,t,x,y,w,h'."""
        level, z, c, t, x, y, w, h = (int(n) for n in tile_name.split(","))
        pix_id = image.getPixelsId()
        with raw_pixels_store(image) as pix:
            pix.setPixelsId(pix_id, False, {"omero.group": "-1"})
            pix.setResolutionLevel(level)
            tile = pix.getTile(z, c, t, x, y, w, h)
            tile = np.frombuffer(tile, dtype=np.uint8)
            tile = tile.reshape((h, w))
            return tile

    lazy_reader = delayed(get_tile)

    def get_lazy_big_plane(level_id, level_desc, z, c, t):
        size_x = level_desc.sizeX
        size_y = level_desc.sizeY
        cols = ceil(size_x / tile_w)
        rows = ceil(size_y / tile_h)
        lazy_rows = []
        for row in range(rows):
            lazy_row = []
            for col in range(cols):
                x = col * tile_w
                y = row * tile_h
                w = min(tile_w, size_x - x)
                h = min(tile_h, size_y - y)
                tile_name = f"{level_id},{z},{c},{t},{x},{y},{w},{h}"
                lazy_tile = da.from_delayed(
                    lazy_reader(tile_name), shape=(h, w), dtype=dtype
                )
                lazy_row.append(lazy_tile)
            lazy_row = da.concatenate(lazy_row, axis=1)
            lazy_rows.append(lazy_row)
        return da.concatenate(lazy_rows, axis=0)

    pyramid = []
    levels_desc = image._re.getResolutionDescriptions()
    for level, level_desc in enumerate(levels_desc):
        level_id = len(levels_desc) - level - 1
        # 5D stack: TCZXY
        t_stacks = []
        for t in range(size_t):
            c_stacks = []
            for c in range(size_c):
                z_stack = []
                for z in range(size_z):
                    z_stack.append(get_lazy_big_plane(level_id, level_desc, z, c, t))
                c_stacks.append(da.stack(z_stack))
            t_stacks.append(da.stack(c_stacks))
        pyramid.append(da.stack(t_stacks))

    return pyramid
