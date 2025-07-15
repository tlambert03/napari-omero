from contextlib import contextmanager
from math import ceil
from typing import Optional

import dask.array as da
import numpy as np
from dask.delayed import delayed
from napari.types import LayerData
from napari.utils.colormaps import ensure_colormap
from omero_marshal import get_encoder
from napari.utils.notifications import show_warning

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


def load_omero(conn: BlitzGateway, image: ImageWrapper) -> list[LayerData]:
    """Retrieve ROIs from an OMERO image and format them as a single Napari layer."""
    roi_service = conn.getRoiService()
    result = roi_service.findByImage(image.getId(), None)
    img_id = image.getId()

    # Lists to store properties for all shapes
    all_coords = []
    all_shape_types = []
    all_comments = []
    all_roi_ids = []
    all_shape_ids = []
    all_z_indices = []
    all_t_indices = []
    all_edge_colors = []
    all_face_colors = []

    # Lists to store properties for all shapes
    point_coords = []
    point_comments = []
    point_shape_ids = []
    point_roi_ids = []
    point_z_indices = []
    point_t_indices = []
    point_edge_colors = []
    point_face_colors = []

    # Get Z and T dimension ranges for the image
    size_z = range(image.getSizeZ())
    size_t = range(image.getSizeT())

    # Get physical pixel sizes; default to 1 if not defined
    size_x = image.getPixelSizeX() or 1
    size_y = image.getPixelSizeY() or 1
    pixel_size_z = image.getPixelSizeZ() or 1

    # Loop through all ROIs
    for roi in result.rois:
        roi_id = roi.getId().getValue()
        # Loop through all shapes in each ROI
        for shape in roi.copyShapes():
            if shape is None:
                show_warning("Encountered an empty (None) shape skipping.")
                continue
            shape_type = shape.__class__.__name__

            shape_id = shape.getId().getValue()
            labels = shape.getTextValue()
            comment = labels.getValue() if labels else ""

            theZ = shape.getTheZ()
            z_values = [theZ.getValue()] if theZ else list(size_z)
            theT = shape.getTheT()
            t_values = [theT.getValue()] if theT else list(size_t)

            edge_color = shape.getStrokeColor()
            fill_color = shape.getFillColor()
            if shape_type != "PointI":
                # Parse shape to Napari-compatible format
                parsed = parse_omero_shape(shape)
                if parsed is None:
                    show_warning(f"Unsupported OMERO shape skipped: {shape_type}")
                    continue

                coords_2d, meta, _ = parsed

                # For all combinations of T and Z, create coords
                for t_index in t_values:
                    for z_index in z_values:
                        coords_4d = []
                        for y, x in coords_2d:
                            coords_4d.append([t_index, z_index, y, x])

                        # Append data for Napari
                        all_coords.append(coords_4d)
                        all_shape_types.append(meta["shape_type"])
                        all_comments.append(comment)
                        all_roi_ids.append(roi_id)
                        all_shape_ids.append(shape_id)
                        all_z_indices.append(z_index)
                        all_t_indices.append(t_index)
                        all_edge_colors.append(omero_color_to_hex(edge_color))
                        all_face_colors.append(omero_color_to_hex(fill_color))

                if not all_coords:
                    return []

            elif shape_type == "PointI":
                x = float(shape.getX().getValue())
                y = float(shape.getY().getValue())

                for t_index in t_values:
                    for z_index in z_values:
                        point_coords.append([t_index, z_index, y, x])
                        point_comments.append(comment)
                        point_shape_ids.append(shape_id)
                        point_roi_ids.append(roi_id)
                        point_z_indices.append(z_index)
                        point_t_indices.append(t_index)
                        point_edge_colors.append(omero_color_to_hex(edge_color))
                        point_face_colors.append(omero_color_to_hex(fill_color))

                if not point_coords:
                    return []

    # ---- Create layers list ----
    layers = []

    # Add shapes layer if available
    if all_coords:
        # Define a single metadata dictionary for the layer
        roi_layer_meta = {
            "name": f"OMERO ROIs {img_id}",
            "shape_type": all_shape_types,
            "edge_width": 1,
            "edge_color": all_edge_colors,
            "face_color": all_face_colors,
            "scale": (1, pixel_size_z, size_y, size_x),
            "text": {
                "string": "{comment}",
                "size": 7,
                "color": "white",
                "anchor": "center",
            },
            "features": {
                "comment": np.array(all_comments, dtype=object),
                "roi_id": np.array(all_roi_ids, dtype=object),
                "shape_id": np.array(all_shape_ids, dtype=object),
                "z_index": np.array(all_z_indices, dtype=int),
                "t_index": np.array(all_t_indices, dtype=int),
                "image_id": np.full(len(all_coords), img_id, dtype=int),
                },
        }

        layers.append((all_coords, roi_layer_meta, "shapes"))

    # Add points layer if available
    if point_coords:
        point_layer_meta = {
            "name": f"OMERO Points {img_id}",
            "symbol": "o",
            "border_color": point_edge_colors,
            "face_color": point_face_colors,
            "size": 5,
            "scale": (1, pixel_size_z, size_y, size_x),
            "text": {"string": "{comment}", "size": 7, "color": "yellow"},
            "features": {
                "comment": np.array(point_comments, dtype=object),
                "roi_id": np.array(point_roi_ids, dtype=object),
                "shape_id": np.array(point_shape_ids, dtype=object),
                "z_index": np.array(point_z_indices, dtype=int),
                "t_index": np.array(point_t_indices, dtype=int),
                "image_id": np.full(len(point_coords), img_id, dtype=int),
            },
        }
        layers.append((point_coords, point_layer_meta, "points"))

    return layers


def omero_color_to_hex(color_val) -> str:
    """Convert OMERO ARGB int to hex color string for Napari."""
    if color_val is None:
        return "white"

    if hasattr(color_val, "getValue"):
        color_val = color_val.getValue()

    # Convert signed to unsigned 32-bit
    val = color_val & 0xFFFFFFFF

    # Extract RGBA
    r = (val >> 24) & 0xFF
    g = (val >> 16) & 0xFF
    b = (val >> 8) & 0xFF
    a = val & 0xFF

    hexa_decimal = f"#{r:02X}{g:02X}{b:02X}"

    return hexa_decimal


def parse_omero_shape(shape) -> Optional[LayerData]:
    """Convert an OMERO shape into a Napari-compatible format."""
    shape_type = shape.__class__.__name__
    if shape_type == "RectangleI":
        # Get position and size
        x = float(shape.getX().getValue())
        y = float(shape.getY().getValue())
        w = float(shape.getWidth().getValue())
        h = float(shape.getHeight().getValue())

        # Coordinates for the rectangle corners in (y, x)
        coords = [[y, x], [y, x + w], [y + h, x + w], [y + h, x]]
        meta = {"shape_type": "rectangle", "name": "ROI_Rectangle"}
        return (coords, meta, "shapes")

    elif shape_type == "PolygonI":
        points = shape.getPoints().getValue()
        coords = [
            [float(y), float(x)]
            for x, y, *_ in (
                p.split(",") for p in points.split(" ")
            )
        ]
        meta = {"shape_type": "polygon", "name": "ROI_Polygon"}
        return (coords, meta, "shapes")

    elif shape_type == "EllipseI":
        cx = float(shape.getX().getValue())
        cy = float(shape.getY().getValue())
        rx = float(shape.getRadiusX().getValue())
        ry = float(shape.getRadiusY().getValue())

        # Compute four corner points of the bounding box
        top_left = [cy - ry, cx - rx]
        top_right = [cy - ry, cx + rx]
        bottom_right = [cy + ry, cx + rx]
        bottom_left = [cy + ry, cx - rx]

        coords = [top_left, top_right, bottom_right, bottom_left]
        meta = {"shape_type": "ellipse", "name": "ROI_Ellipse"}
        return (coords, meta, "shapes")

    # Return None if shape type not supported
    return None

