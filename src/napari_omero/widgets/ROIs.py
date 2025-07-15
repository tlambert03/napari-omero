import warnings

import napari.viewer
from magicgui import magic_factory
from napari.layers import Image, Labels, Shapes
from napari.utils.notifications import show_info

from napari_omero.plugins.omero import save_rois
from napari_omero.plugins.loaders import load_rois, load_points
from napari_omero.utils import lookup_obj
from magicgui.widgets import PushButton
from omero.cli import ProxyStringType

from .gateway import QGateWay
import re

def _init(widget):
    shape_load_button = PushButton(text="Load ROIs from OMERO")
    widget.insert(1, shape_load_button)
    widget.shape_load_button = shape_load_button

    points_load_button = PushButton(text="Load points from OMERO")
    widget.insert(2, points_load_button)
    widget.points_load_button = points_load_button

    @shape_load_button.clicked.connect
    def _load_rois_from_omero():
        viewer = napari.viewer.current_viewer()
        image_layer = viewer.layers.selection.active

        if not image_layer or "omero" not in image_layer.metadata:
            show_info("No OMERO metadata found in selected layer.")
            return

        gateway = QGateWay()
        layer_name = image_layer.name
        image_id = int(layer_name.split(":")[0])

        image_wrapper = gateway.conn.getObject("Image", image_id)
        roi_layers = load_rois(gateway.conn, image_wrapper)

        coords_flag = False
        for coords, meta, _ in roi_layers:
            coords_flag = True
            viewer.add_shapes(coords, **meta)

        if coords_flag:
            show_info(f"Loaded {len(coords)} ROIs from OMERO img id {image_id}.")
        else:
            show_info(f"No ROIs found for OMERO image id {image_id}.")


    @points_load_button.clicked.connect
    def _load_points_from_omero():
        viewer = napari.viewer.current_viewer()
        image_layer = viewer.layers.selection.active

        if not image_layer or "omero" not in image_layer.metadata:
            show_info("No OMERO metadata found in selected layer.")
            return

        gateway = QGateWay()
        layer_name = image_layer.name
        image_id = int(layer_name.split(":")[0])

        image_wrapper = gateway.conn.getObject("Image", image_id)
        point_layers = load_points(gateway.conn, image_wrapper)

        points = False
        for point_coords, meta, _ in point_layers:
            points = True
            viewer.add_points(point_coords, **meta)

        if points:
            show_info(f"Loaded {len(point_coords)} points from OMERO img id {image_id}.")
        else:
            show_info(f"No points found for OMERO image id {image_id}.")


@magic_factory(
    omero_image={"label": "OMERO ROI Manager"},
    call_button="Upload Annotations to OMERO",
    widget_init=_init
)
def save_rois_to_OMERO(omero_image: Image) -> None:
    """Upload annotations for a chosen image to OMERO.

    Parameters
    ----------
    omero_image: Image
        An image layer loaded from OMERO.
        Layer metadata has stored OMERO image ID.
        Annotations will be uploaded to the OMERO server as ROI for that image ID.

    Returns
    -------
    None
    """
    # check if 'omero' field is in metadata
    if "omero" not in omero_image.metadata:
        warnings.warn("No OMERO metadata found in selected layer.", stacklevel=2)
        return

    # assert that layer is 4D if it is a labels layer
    if isinstance(omero_image, Labels) and omero_image.ndim != 4:
        raise ValueError(
            "Labels layer must be 4D (time, z, y, x) to be uploaded to OMERO."
        )

    gateway = QGateWay()
    image_id = omero_image.metadata["omero"]["@id"]

    image_wrapper = lookup_obj(
        gateway.conn, ProxyStringType("Image")(f"Image:{image_id}")
    )

    viewer = napari.viewer.current_viewer()
    save_rois(viewer=viewer, image=image_wrapper)

    trg = image_wrapper.getName()
    show_info(f"All annotation layers uploaded to OMERO image id {image_id}: {trg}")
