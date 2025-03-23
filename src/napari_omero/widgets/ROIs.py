import json
from typing import Optional

import numpy as np
import pyperclip
from napari.layers import Labels, Shapes
from omero_rois import mask_from_binary_image
from qtpy.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from napari_omero.utils import lookup_obj
from omero.cli import ProxyStringType
from omero.model import RoiI

from .gateway import QGateWay


class ROIWidget(QWidget):
    def __init__(self, viewer: "napari.viewer.Viewer"):  # noqa: F821
        super().__init__()

        self.viewer = viewer
        self.gateway = QGateWay(self)
        self.shapes_layer: Optional[Shapes] = None
        self.labels_layer: Optional[Labels] = None

        layout = QHBoxLayout()
        self.setLayout(layout)

        self.copy_bttn = QPushButton("Copy OMERO metadat")
        self.paste_bttn = QPushButton("Paste OMERO metadata")
        self.upload_bttn = QPushButton("Upload to OMERO")

        layout.addWidget(self.copy_bttn)
        layout.addWidget(self.paste_bttn)
        layout.addWidget(self.upload_bttn)

        self.copy_bttn.clicked.connect(self._on_copy_metadata)
        self.paste_bttn.clicked.connect(self._on_paste_metadata)
        self.upload_bttn.clicked.connect(self._on_upload_to_omero)

    @property
    def selected_layers(self):
        return list(self.viewer.layers.selection)

    def _on_copy_metadata(self):
        """Create a new shapes layer in the viewer and link to the selected layer."""
        selected_layer = self.selected_layers[0]

        # check if 'omero' field is in metadata
        if "omero" not in selected_layer.metadata:
            return

        # copy to clipboard
        metadata_json = json.dumps(selected_layer.metadata["omero"])
        pyperclip.copy(metadata_json)

    def _on_paste_metadata(self):
        """Create a new labels layer in the viewer and link to the selected layer."""
        selected_layer = self.selected_layers[0]

        if not isinstance(selected_layer, (Shapes, Labels)):
            return

        # paste from clipboard
        metadata_json = pyperclip.paste()
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError:
            print("Failed to decode JSON from clipboard.")
            return

        # clip metadata to relevant fields:
        # ID

        relevant_fields = ["@id"]
        metadata = {key: metadata[key] for key in relevant_fields if key in metadata}

        # update metadata
        selected_layer.metadata["omero"] = metadata

    def _on_upload_to_omero(self):
        if not isinstance(self.selected_layers[0], Labels):
            return

        image_id = self.selected_layers[-1].metadata["omero"]["@id"]
        labels_data = np.asarray(self.selected_layers[0].data)

        updateService = self.gateway.conn.getUpdateService()
        image_wrapper = lookup_obj(
            self.gateway.conn, ProxyStringType("Image")(f"Image:{image_id}")
        )

        roi = RoiI()
        roi.setImage(image_wrapper._obj)

        for label in range(1, labels_data.max() + 1):
            mask = labels_data == label

            rgba = np.random.randint(0, 255, 4)
            rgba[-1] = 128  # opacity
            shape = mask_from_binary_image(mask, raise_on_no_mask=False, rgba=rgba)
            roi.addShape(shape)

        updateService.saveAndReturnObject(roi)
