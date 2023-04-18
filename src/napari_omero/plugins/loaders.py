from math import ceil
from typing import Dict, List, Optional

import dask.array as da
import numpy as np
from dask.delayed import delayed
from napari.types import LayerData
from omero.cli import ProxyStringType
from omero.gateway import BlitzGateway, ImageWrapper
from omero.model import IObject
from vispy.color import Colormap

from ..utils import PIXEL_TYPES, lookup_obj, parse_omero_url, timer
from ..widgets import QGateWay


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

    from ..widgets.login import LoginForm

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


# @timer
def omero_proxy_reader(
    path: str, proxy_obj: Optional[IObject] = None
) -> List[LayerData]:
    gateway = get_gateway(path)

    if proxy_obj.__class__.__name__.startswith("Image"):
        wrapper = lookup_obj(gateway, proxy_obj)
        if isinstance(wrapper, ImageWrapper):
            return load_image_wrapper(wrapper)
    return []


def load_image_wrapper(image: ImageWrapper) -> List[LayerData]:
    meta = get_omero_metadata(image)
    # contrast limits range ... not accessible from plugin interface
    # win_min = channel.getWindowMin()
    # win_max = channel.getWindowMax()
    if image.requiresPixelsPyramid():
        data = get_pyramid_lazy(image)
    else:
        data = get_data_lazy(image)
    return [(data, meta)]


def get_omero_metadata(image: ImageWrapper) -> Dict:
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


def get_pyramid_lazy(image: ImageWrapper) -> List[da.Array]:
    """Get a pyramid of rgb dask arrays, loading tiles from OMERO."""
    size_z = image.getSizeZ()
    size_t = image.getSizeT()
    size_c = image.getSizeC()
    pixels = image.getPrimaryPixels()
    dtype = PIXEL_TYPES.get(pixels.getPixelsType().value, None)

    image._prepareRenderingEngine()
    tile_w, tile_h = image._re.getTileSize()

    def get_tile(tile_name):
        """tile_name is 'level,z,t,x,y,w,h'"""
        # print('get_tile rps', tile_name)
        level, z, c, t, x, y, w, h = (int(n) for n in tile_name.split(","))
        pix = image._conn.c.sf.createRawPixelsStore()
        pix_id = image.getPixelsId()
        try:
            pix.setPixelsId(pix_id, False)
            pix.setResolutionLevel(level)
            tile = pix.getTile(z, c, t, x, y, w, h)
            tile = np.frombuffer(tile, dtype=np.uint8)
            tile = tile.reshape((h, w))
            return tile
        finally:
            pix.close()

    lazy_reader = delayed(get_tile)

    def get_lazy_big_plane(level_id, level_desc, z, c, t):
        size_x = level_desc.sizeX
        size_y = level_desc.sizeY
        cols = ceil(size_x / tile_w)
        rows = ceil(size_y / tile_h)
        # print('level', level, level_id, size_x, size_y)
        print("Cols", cols, "Rows", rows)
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
            print("lazy_row.shape", lazy_row.shape)
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
