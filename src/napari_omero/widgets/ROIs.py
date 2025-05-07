import warnings
import napari
from napari.utils.notifications import show_info
from napari_omero.utils import lookup_obj
from omero.cli import ProxyStringType
from magicgui import magic_factory

from .gateway import QGateWay
from ..plugins.omero import save_rois


@magic_factory(call_button='Upload ROIS to OMERO')
def save_rois_to_OMERO(
        omero_image: napari.layers.Layer
) -> None:
    """
    Upload ROIs for a given image to OMERO.

    omero_image: napari.layers.Image
        An image from OMERO that was loaded into the napari viewer.

    Returns
    -------
    None
    """

    # check if 'omero' field is in metadata
    if "omero" not in omero_image.metadata:
        warnings.warn(
            "No OMERO metadata found in selected layer.",
            stacklevel=2
            )
        return

    # assert that layer is 4D if it is a labels layer
    if isinstance(omero_image, napari.layers.Labels) and omero_image.ndim != 4:
        raise ValueError(
            "Labels layer must be 4D (time, z, y, x) to be uploaded to OMERO."
        )

    gateway = QGateWay()
    image_id = omero_image.metadata["omero"]["@id"]

    image_wrapper = lookup_obj(
        gateway.conn, ProxyStringType("Image")(f"Image:{image_id}")
    )

    viewer = napari.current_viewer()
    save_rois(viewer=viewer, image=image_wrapper)

    src = omero_image.name
    trg = image_wrapper.getName()
    show_info(
        f"ROI layer {src} uploaded to OMERO image {trg}"
    )
