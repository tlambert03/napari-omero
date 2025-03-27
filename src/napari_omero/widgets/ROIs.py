import json
import warnings
from typing import Optional

import numpy as np
import pyperclip
from napari.layers import Labels, Shapes
from napari.viewer import Viewer
from omero_rois import mask_from_binary_image
from qtpy.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from napari_omero.utils import lookup_obj
from omero.cli import ProxyStringType
from omero.model import RoiI

from .gateway import QGateWay


class ROIWidget(QWidget):
    supported_layers = [
        Labels,
    ]

    def __init__(self, viewer: "napari.viewer.Viewer"):  # noqa: F821
        super().__init__()

        self.viewer = viewer
        self.gateway = QGateWay(self)
        self.shapes_layer: Optional[Shapes] = None
        self.labels_layer: Optional[Labels] = None
        self.copied_metadata: dict = None

        self.setup_widget()

    def setup_widget(self):
        # Layouts
        layout_copy_controls = QHBoxLayout()
        layout_layer_hint = QHBoxLayout()
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.selected_layer_hint = QLabel("Selected layer:")
        self.selected_layer_label = QLabel("None")
        layout_layer_hint.addWidget(self.selected_layer_hint)
        layout_layer_hint.addWidget(self.selected_layer_label)

        self.label_link = QLabel("Link selected OMERO image to:")
        self.target_link_dropdown = QComboBox()
        self.link_bttn = QPushButton("Link images!")
        self.upload_bttn = QPushButton("Upload ROIs to OMERO")
        self.status_label = QLabel("")

        layout_copy_controls.addWidget(self.label_link)
        layout_copy_controls.addWidget(self.target_link_drowdown)
        layout_copy_controls.addWidget(self.link_bttn)

        layout.addLayout(layout_layer_hint)
        layout.addLayout(layout_copy_controls)
        layout.addWidget(self.status_label)
        layout.addWidget(self.upload_bttn)

        # connections
        self.link_bttn.clicked.connect(self._on_link_layers)
        self.upload_bttn.clicked.connect(self._on_upload_to_omero)
        self.viewer.layers.events.removed.connect(self._populate_dropdown)
        self.viewer.layers.events.inserted.connect(self._populate_dropdown)
        self.viewer.layers.selection.events.changed.connect(self._on_layer_selected)

        # Key bindings
        self.viewer.bind_key("Control-Shift-c", self._on_copy_metadata)
        self.viewer.bind_key("Control-Shift-v", self._on_paste_metadata)

    @property
    def selected_layer(self):
        if len(self.viewer.layers.selection) == 0:
            return None
        return next(iter(self.viewer.layers.selection))

    def _on_layer_selected(self):
        if self.selected_layer is None:
            self.selected_layer_label.setText("None")
        else:
            self.selected_layer_label.setText(self.selected_layer.name)

    def _populate_dropdown(self):
        currently_selected = self.target_link_drowdown.currentText()
        self.target_link_drowdown.clear()

        for layer in self.viewer.layers:
            if type(layer) in self.supported_layers:
                self.target_link_drowdown.addItem(layer.name)

        # restore selection if possible
        index = self.target_link_drowdown.findText(currently_selected)
        if index != -1:
            self.target_link_drowdown.setCurrentIndex(index)

    def _on_link_layers(self):
        target_layer = self.viewer.layers[self.target_link_drowdown.currentText()]

        if type(target_layer) not in self.supported_layers:
            warnings.warn("Target layer type currently not supported.", stacklevel=2)
            return

        # check if 'omero' field is in metadata
        if "omero" not in self.selected_layer.metadata:
            warnings.warn("No OMERO metadata found in selected layer.", stacklevel=2)
            return

        target_layer.metadata["omero"] = self.selected_layer.metadata["omero"]
        self.status_label.setText(f"Metadata pasted to {target_layer.name}")

    @Viewer.bind_key("Control-Shift-c", overwrite=True)
    def _on_copy_metadata(self, viewer):
        """Create a new shapes layer in the viewer and link to the selected layer."""
        print("copying metadata")

        # check if 'omero' field is in metadata
        if "omero" not in self.selected_layer.metadata:
            warnings.warn("No OMERO metadata found in selected layer.", stacklevel=2)
            return

        # copy to clipboard
        metadata_json = json.dumps(self.selected_layer.metadata["omero"])
        pyperclip.copy(metadata_json)

        self.status_label.setText(f"Metadata copied from {self.selected_layer.name}")

    @Viewer.bind_key("Control-Shift-v", overwrite=True)
    def _on_paste_metadata(self, viewer):
        """Create a new labels layer in the viewer and link to the selected layer."""
        print("pasting metadata")

        target_layer = self.viewer.layers[self.target_link_drowdown.currentText()]

        # paste from clipboard
        metadata_json = pyperclip.paste()
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError:
            print("Failed to decode JSON from clipboard.")
            return

        # clip metadata to relevant fields:
        # ID is (currently) the only field that is relevant for linking
        relevant_fields = ["@id"]
        metadata = {key: metadata[key] for key in relevant_fields if key in metadata}

        # update metadata
        target_layer.metadata["omero"] = metadata
        self.status_label.setText(f"Metadata pasted to {target_layer.name}")

    def _on_upload_to_omero(self):
        if type(self.selected_layer) not in self.supported_layers:
            warnings.warn("Selected layer type currently not supported.", stacklevel=2)
            return

        image_id = self.selected_layer.metadata["omero"]["@id"]
        labels_data = np.asarray(self.selected_layer.data)

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

        self.status_label.setText(
            f"ROIs from <{self.selected_layer.name}> uploaded to OMERO (ID: #{image_id})"
        )
