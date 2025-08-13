from typing import Optional

from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import QIcon, QImage, QPixmap
from qtpy.QtWidgets import QListWidget, QListWidgetItem

from .gateway import QGateWay
from .tree_model import OMEROTreeItem

THUMBSIZE = 96


class ThumbItemWidget(QWidget):
    """Custom widget that displays an icon with a table of properties below."""
    
    def __init__(self, icon: QIcon, wrapper, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        
        layout = QVBoxLayout(self)

        # Icon label
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(THUMBSIZE, THUMBSIZE))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        # Name label
        name_label = QLabel(wrapper.getName())
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet("font-weight: bold; color: white;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        # Properties to display
        properties = [
            ("ID", str(wrapper.getId())),
            ("Timepoints", f"{wrapper.getSizeT()}"),
            ("Channels", f"{wrapper.getSizeC()}"),
            ("Shape", f"{wrapper.getSizeZ()}x{wrapper.getSizeY()}x{wrapper.getSizeX()}"),
        ]

        # Properties table
        table = QTableWidget(len(properties), 2)
        table.setHorizontalHeaderLabels(["Property", "Value"])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        for row, (prop, value) in enumerate(properties):
            table.setItem(row, 0, QTableWidgetItem(prop))
            table.setItem(row, 1, QTableWidgetItem(value))
        
        layout.addWidget(table)

        # Resize table to content
        table.resizeRowsToContents()
        table.resizeColumnToContents(0)
        table.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        table.setMaximumWidth(THUMBSIZE)  # Allow some padding for the table
        
        # Set size policy for the entire widget to be flexible
        #self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFixedHeight(THUMBSIZE + len(properties) * 20 + 70)
        self.setFixedWidth(THUMBSIZE)

class ThumbGrid(QListWidget):
    def __init__(self, gateway: QGateWay, parent=None):
        super().__init__(parent)
        self.gateway = gateway
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(THUMBSIZE, THUMBSIZE))
        self.setResizeMode(QListWidget.Adjust)
        self.loader = None
        self.setStyleSheet("QListView {font-size: 8px; background: black};")
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
        name = wrapper.getName()
        if len(name) > 18:
            name = f"{name[:15]}..."
        item = QListWidgetItem(icon, name)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
        )
        item.wrapper = wrapper
        self._item_map[wrapper.getId()] = item
        self.addItem(item)
        if (
            isinstance(self._current_item, OMEROTreeItem)
            and self._current_item.isImage()
        ):
            self.select_image()
