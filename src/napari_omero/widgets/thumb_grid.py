from typing import Optional

from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import QIcon, QImage, QPixmap
from qtpy.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView
)

from .gateway import QGateWay
from .tree_model import OMEROTreeItem

THUMBSIZE = 192


class ThumbItemWidget(QWidget):
    """Custom widget that displays an icon with a table of properties below."""

    def __init__(self, icon: QIcon, wrapper, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper

        layout = QVBoxLayout(self)

        # Icon label
        icon_label = QLabel()
        pixmap = icon.pixmap(THUMBSIZE, THUMBSIZE)
        icon_height = pixmap.height()
        icon_width = pixmap.width()
        icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Name label
        name_label = QLabel(wrapper.getName())
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet("font-weight: bold; color: white;")
        name_label.setWordWrap(True)
        name_label.adjustSize()

        # Properties to display
        properties = [
            ("ID", str(wrapper.getId())),
            ("T", f"{wrapper.getSizeT()}"),
            ("Ch", f"{wrapper.getSizeC()}"),
            (
                "Shape",
                f"{wrapper.getSizeZ()}x{wrapper.getSizeY()}x{wrapper.getSizeX()}",
            ),
        ]

        # Properties table
        table = QTableWidget(len(properties), 2)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for row, (prop, value) in enumerate(properties):
            table.setItem(row, 0, QTableWidgetItem(prop))
            table.setItem(row, 1, QTableWidgetItem(value))


        # Resize table to content
        table.resizeRowsToContents()
        table.resizeColumnToContents(0)
        table.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        table.setMaximumWidth(THUMBSIZE)  # Allow some padding for the table

        # Set size policy for the entire widget to be flexible
        # self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFixedHeight(icon_height + len(properties) * 20 + 70)
        self.setFixedWidth(THUMBSIZE)
        layout.addWidget(icon_label)
        layout.addWidget(name_label)
        layout.addWidget(table)
        self.setLayout(layout)

        # # Set size boundaries
        self.setMinimumWidth(icon_width)
        self.setMaximumWidth(192)
        self.setFixedHeight(icon_height + name_label.height() + table.height())




class ThumbGrid(QListWidget):
    def __init__(self, gateway: QGateWay, parent=None):
        super().__init__(parent)
        self.gateway = gateway
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(THUMBSIZE, THUMBSIZE))
        self.setResizeMode(QListWidget.Adjust)
        self.loader = None
        self.setStyleSheet("QListView {font-size: 8px; background: black};")
        self.setDragDropMode(QListWidget.DragDropMode.NoDragDrop)
        self.setSpacing(4)
        self._current_dataset: Optional[OMEROTreeItem] = None
        self._current_item: Optional[OMEROTreeItem] = None
        self._item_map: dict[str, QListWidgetItem] = {}

    def set_item(self, item: OMEROTreeItem):
        if item == self._current_item:
            return

        self._current_item = item

        dataset = None
        if item.isDataset():
            dataset = item
        elif item.isImage():
            dataset = item.parent()
        else:
            self._current_dataset = None

        if dataset:
            self.set_dataset(dataset)
            self.show()
        if item.isImage():
            self.select_image()

    def select_image(self):
        if self._current_item is not None:
            wrapper = self._current_item.wrapper
            item = self._item_map.get(wrapper.getId())
            if item:
                self.setCurrentItem(item)

    def set_dataset(self, item):
        if not self.gateway.isConnected():
            return

        if item == self._current_dataset:
            return

        self._current_dataset = item

        def yield_thumbs(conn):
            self.clear()
            self._item_map.clear()
            for img in item.wrapper.listChildren():
                for byte in conn.getThumbnailSet([img.getId()], THUMBSIZE).values():
                    yield byte, img

        return self.gateway._submit(
            yield_thumbs,
            self.gateway.conn,
            _wait=False,
            _connect={"yielded": self.add_thumb_bytes},
        )

    def add_thumb_bytes(self, result):
        bytes_, wrapper = result
        img = QImage()
        img.loadFromData(bytes_)
        icon = QIcon(QPixmap.fromImage(img))

        # Create a QListWidgetItem
        item = QListWidgetItem()
        item.wrapper = wrapper

        # Create custom widget
        thumb_widget = ThumbItemWidget(icon, wrapper)

        # Set item size to match widget size
        item.setSizeHint(thumb_widget.size())

        # Add item to list and set custom widget
        self.addItem(item)
        self.setItemWidget(item, thumb_widget)

        # Store in item map
        self._item_map[wrapper.getId()] = item

        if (
            isinstance(self._current_item, OMEROTreeItem)
            and self._current_item.isImage()
        ):
            self.select_image()
