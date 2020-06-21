from qtpy.QtWidgets import QTreeView, QVBoxLayout, QWidget
from qtpy.QtCore import Qt

from .login import LoginForm
from .thumb_grid import ThumbGrid
from .tree_model import OMEROTreeModel


class OMEROWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.tree = QTreeView(self)
        self.tree.setHeaderHidden(True)
        # self.tree.setSelectionMode(QTreeView.MultiSelection)
        self.model = OMEROTreeModel()
        self.thumb_grid = ThumbGrid(self)
        self.login = LoginForm(self)
        self.login.setWindowFlags(self.login.windowFlags() & ~Qt.Dialog)
        self.login.connected.connect(self._on_new_connection)
        self.tree.setModel(self.model)
        self.tree.selectionModel().selectionChanged.connect(self.onSelectionChange)
        self.thumb_grid.itemSelectionChanged.connect(self._on_image_selected)
        layout = QVBoxLayout(self)
        layout.addWidget(self.login)
        layout.addWidget(self.tree)
        layout.addWidget(self.thumb_grid)

    def _on_new_connection(self, conn):
        self.model.set_connection(conn)
        self.thumb_grid.set_connection(conn)
        self.login.hide()

    @property
    def viewer(self):
        if hasattr(self.parent(), "qt_viewer"):
            return self.parent().qt_viewer.viewer
        return None

    def _on_image_selected(self):
        if not self.thumb_grid.selectedItems():
            return
        for layer in self.viewer.layers:
            self.viewer.layers.remove(layer)
        wrapper = self.thumb_grid.selectedItems()[0].wrapper
        type_ = wrapper.__class__.__name__[1:-7]
        id_ = wrapper.getId()
        self.viewer.open(f"{type_}:{id_}", plugin="omero")

    def onSelectionChange(self, selected, deselected):
        item = self.model.itemFromIndex(selected.indexes()[0])
        if item.isDataset():
            self.thumb_grid.set_thumbs(item)
        elif item.isImage():
            self.thumb_grid.set_thumbs(item.parent())
