import warnings

import napari.viewer
from magicgui import magic_factory
from magicgui.widgets import PushButton
from napari.layers import Image, Labels
from napari.utils.notifications import show_info

from napari_omero.plugins.loaders import load_rois
from napari_omero.plugins.omero import save_rois
from napari_omero.utils import lookup_obj
from omero.cli import ProxyStringType

from .gateway import QGateWay


def _init(widget):
    shape_load_button = PushButton(text="Load Annotations from OMERO")
    widget.insert(1, shape_load_button)
    widget.shape_load_button = shape_load_button

    @shape_load_button.clicked.connect
    def _load_rois_from_omero():
        viewer = napari.viewer.current_viewer()
        image_layer = viewer.layers.selection.active

        if not image_layer or "omero" not in image_layer.metadata:
            show_info("No OMERO metadata found in selected layer.")
            return

        gateway = QGateWay()
        layer_name = image_layer.name
        img_id = int(layer_name.split(":")[0])

        image_wrapper = gateway.conn.getObject("Image", img_id)
        points_coords, points_meta = load_rois(
            gateway.conn, image_wrapper, load_points=True
        )
        shapes_coords, shapes_meta = load_rois(
            gateway.conn, image_wrapper, load_points=False
        )

        if points_meta is None and shapes_meta is None:
            show_info(f"No ROIs or points found for OMERO image id {img_id}.")
            return
        if shapes_meta:
            viewer.add_shapes(shapes_coords, **shapes_meta)
        if points_meta:
            viewer.add_points(points_coords, **points_meta)


@magic_factory(
    omero_image={"label": "OMERO ROI Manager"},
    call_button="Upload Annotations to OMERO",
    widget_init=_init,
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
