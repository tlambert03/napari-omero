from qtpy.QtCore import (
    QCoreApplication,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    Qt,
)
from qtpy.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from superqt.utils import signals_blocked

from omero.gateway import BlitzObjectWrapper, ExperimenterGroupWrapper

from .gateway import QGateWay
from .login import LoginForm
from .thumb_grid import ThumbGrid
from .tree_model import OMEROTreeModel


class OMEROWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._group_wrapper: ExperimenterGroupWrapper | None = None

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

        self.group_combo = QComboBox()
        self.group_combo.currentIndexChanged.connect(self._on_group_changed)
        self.group_widget = QWidget()
        self.group_widget.setLayout(QHBoxLayout())
        lbl = QLabel("Group:")
        lbl.setFixedWidth(50)
        self.group_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.group_widget.layout().addWidget(lbl)
        self.group_widget.layout().addWidget(self.group_combo)
        self.group_widget.hide()

        self.user_combo = QComboBox()
        self.user_combo.currentIndexChanged.connect(self._on_user_changed)
        self.user_widget = QWidget()
        self.user_widget.setLayout(QHBoxLayout())
        lbl = QLabel("User:")
        lbl.setFixedWidth(50)
        self.user_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.user_widget.layout().addWidget(lbl)
        self.user_widget.layout().addWidget(self.user_combo)
        self.user_widget.hide()

        layout.addWidget(self.status)
        layout.addWidget(self.group_widget)
        layout.addWidget(self.user_widget)
        layout.addWidget(self.splitter)
        layout.addWidget(self.disconnect_button)

        self.splitter.addWidget(self.login)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.thumb_grid)
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
        self.tree.setModel(None)
        self.tree.setModel(self.model)
        self.tree.selectionModel().selectionChanged.connect(self._on_tree_selection)

    def _on_disconnect(self):
        """Hide project widgets (tree, thumb grid) and disconnect button."""
        self.status.setText("Not connected")
        self.gateway.close()
        self.disconnect_button.hide()
        self.tree.hide()
        self.thumb_grid.hide()
        self.group_widget.hide()
        self.user_widget.hide()

        self._setup_tree()

    def _on_connect(self):
        """Show project tree and disconnect button."""
        self.status.setText(f"{self.gateway._user}@{self.gateway._host}")
        self.status.show()
        self.tree.show()
        self.group_widget.show()
        self.user_widget.show()
        self._group_wrapper = self.gateway.conn.getGroupFromContext()
        with signals_blocked(self.group_combo), signals_blocked(self.user_combo):
            self._update_group_combo()
        self._on_user_changed()
        self.disconnect_button.show()

    def _update_group_combo(self):
        with signals_blocked(self.group_combo):
            self.group_combo.clear()
            self.group_combo.addItem("All", None)
            for group in self.gateway.conn.getGroupsMemberOf():
                self.group_combo.addItem(group.getName(), group.getId())
        if self._group_wrapper is not None:
            self.group_combo.setCurrentText(self._group_wrapper.getName())
            self._on_group_changed()

    def _update_user_combo(self):
        # List the group owners and other members
        current_user = self.user_combo.currentText()
        with signals_blocked(self.user_combo):
            self.user_combo.clear()
            self.user_combo.addItem("All", None)
            if self._group_wrapper is not None:
                self.user_combo.insertSeparator(self.user_combo.count())
                owners, members = self._group_wrapper.groupSummary()
                for o in owners:
                    self.user_combo.addItem(o.getFullName(), o.getId())
                self.user_combo.insertSeparator(self.user_combo.count())
                for m in members:
                    self.user_combo.addItem(m.getFullName(), m.getId())

            if current_user and self.user_combo.findText(current_user) > -1:
                self.user_combo.setCurrentText(current_user)
            else:
                user = self.gateway.conn.getUser()
                self.user_combo.setCurrentText(user.getFullName())
        self._on_user_changed()

    def _on_group_changed(self):
        group_id = self.group_combo.currentData()
        if group_id is None:
            group_id = -1
        conn = self.gateway.conn
        conn.SERVICE_OPTS.setOmeroGroup(group_id)
        group = conn.getAdminService().getGroup(group_id)
        self._group_wrapper = ExperimenterGroupWrapper(conn, group)
        self._update_user_combo()

    def _on_user_changed(self):
        group_id = self.group_combo.currentData()
        user_id = self.user_combo.currentData()
        self.model.submit_get_projects(owner=user_id, group=group_id)

    def _on_tree_selection(self, selected: QItemSelection, deselected: QItemSelection):
        indices = selected.indexes()
        if not indices:
            return

        item = self.model.itemFromIndex(indices[0])
        self.thumb_grid.set_item(item)

        if item.isImage():
            # avoid loading the same image twice
            if (
                self.thumb_grid.currentItem()
                and self.thumb_grid.currentItem().wrapper == item.wrapper
            ):
                return
            QCoreApplication.processEvents()
            self.load_image(item.wrapper)

    def load_image(self, wrapper: BlitzObjectWrapper):
        if not self.viewer:
            return

        type_ = wrapper.__class__.__name__[1:-7]
        id_ = wrapper.getId()
        self.viewer.open(f"omero://{type_}:{id_}", plugin="napari-omero")
