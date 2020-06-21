from qtpy.QtWidgets import QListWidget, QListWidgetItem
from qtpy.QtGui import QPixmap, QImage, QIcon
from qtpy.QtCore import QSize, Qt
from napari.qt import thread_worker

THUMBSIZE = 96


@thread_worker
def yield_thumbs(conn, child_iterator):
    for img in child_iterator:
        for byte in conn.getThumbnailSet([img.getId()], THUMBSIZE).values():
            yield byte, img


class ThumbGrid(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(THUMBSIZE, THUMBSIZE))
        self.setResizeMode(QListWidget.Adjust)
        self._conn = None
        self.loader = None
        self.setStyleSheet("QListWidget {font-size: 8px}")
        self.setSpacing(4)

    def set_thumbs(self, item):
        if not (self._conn and self._conn.isConnected()):
            return
        self.clear()
        self.loader = yield_thumbs(self._conn, item.wrapper.listChildren())
        self.loader.yielded.connect(self.add_thumb_bytes)
        self.loader.start()

    def add_thumb_bytes(self, result):
        bytes_, wrapper = result
        img = QImage()
        img.loadFromData(bytes_)
        icon = QIcon(QPixmap.fromImage(img))
        name = wrapper.getName()
        if len(name) > 18:
            name = name[:15] + "..."
        item = QListWidgetItem(icon, name)
        item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        item.wrapper = wrapper
        self.addItem(item)

    def set_connection(self, conn):
        self._conn = conn
