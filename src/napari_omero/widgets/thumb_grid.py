from typing import Optional

from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import QIcon, QImage, QPixmap
from qtpy.QtWidgets import QListWidget, QListWidgetItem

from .gateway import QGateWay
from .tree_model import OMEROTreeItem

THUMBSIZE = 96


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
