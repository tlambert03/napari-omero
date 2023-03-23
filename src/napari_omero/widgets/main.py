from omero.gateway import BlitzObjectWrapper
from qtpy.QtCore import (
    QCoreApplication,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    Qt,
)
from qtpy.QtWidgets import (
    QLabel,
    QPushButton,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from .gateway import QGateWay
from .login import LoginForm
from .thumb_grid import ThumbGrid
from .tree_model import OMEROTreeModel


class OMEROWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.gateway = QGateWay(self)
        self.tree = QTreeView(self)
        self.tree.setHeaderHidden(True)
        # self.tree.setSelectionMode(QTreeView.MultiSelection)
        self.thumb_grid = ThumbGrid(self.gateway, self)
        self.thumb_grid.hide()
        self.login = LoginForm(self.gateway, self)
        self.login.setWindowFlags(self.login.windowFlags() & ~Qt.Dialog)

        self._setup_tree()

        self.thumb_grid.itemSelectionChanged.connect(self._on_thumbnail_selected)
        layout = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Vertical, self)
        self.status = QLabel(self)
        self.status.hide()
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("QLabel{color: #AAA;}")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.hide()

        layout.addWidget(self.status)
        layout.addWidget(self.splitter)

        self.splitter.addWidget(self.login)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.thumb_grid)
        self.splitter.addWidget(self.disconnect_button)
        self.gateway.connected.connect(self._on_connect)
        self.disconnect_button.clicked.connect(self._on_disconnect)

    @property
    def viewer(self):
        from napari.utils._magicgui import find_viewer_ancestor

        return find_viewer_ancestor(self)

    def _on_thumbnail_selected(self):
        if not self.thumb_grid.selectedItems():
            return
        wrapper = self.thumb_grid.selectedItems()[0].wrapper
        index: QModelIndex = self.model._wrapper_map.get(wrapper.getId())
        if index:
            self.tree.selectionModel().select(
                index,
                QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
            )
        self.load_image(wrapper)

    def _setup_tree(self):
        """Set up QTreeView with a fresh tree model."""
        self.model = OMEROTreeModel(self.gateway, self)
        self.tree.setModel(self.model)
        self.tree.selectionModel().selectionChanged.connect(self._on_tree_selection)

    def _on_disconnect(self):
        """Hide project widgets (tree, thumb grid) and disconnect button."""
        self.status.setText("Not connected")
        self.gateway.close()
        self.disconnect_button.hide()
        self.tree.hide()
        self.thumb_grid.hide()

        self._setup_tree()

    def _on_connect(self):
        """Show project tree and disconnect button."""
        self.status.setText(f"{self.gateway._user}@{self.gateway._host}")
        self.status.show()
        self.tree.show()
        self.disconnect_button.show()

    def _on_tree_selection(self, selected: QItemSelection, deselected: QItemSelection):
        item = self.model.itemFromIndex(selected.indexes()[0])
        self.thumb_grid.set_item(item)

        if item.isImage():
            QCoreApplication.processEvents()
            self.load_image(item.wrapper)

    def load_image(self, wrapper: BlitzObjectWrapper):
        self.viewer.layers.select_all()
        self.viewer.layers.remove_selected()

        type_ = wrapper.__class__.__name__[1:-7]
        id_ = wrapper.getId()
        self.viewer.open(f"omero://{type_}:{id_}", plugin="napari-omero")
