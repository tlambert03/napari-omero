from napari.qt import create_worker
from omero.gateway import (
    BlitzGateway,
    BlitzObjectWrapper,
    _DatasetWrapper,
    _ImageWrapper,
)
from qtpy.QtCore import QModelIndex
from qtpy.QtGui import QStandardItem, QStandardItemModel


class OMEROTreeItem(QStandardItem):
    def __init__(self, wrapper: BlitzObjectWrapper):
        super().__init__()
        self.wrapper = wrapper
        self._has_fetched = False
        if self.hasChildren():
            self.setText(f"{self.wrapper.getName()} ({self.numChildren()})")
        else:
            self.setText(f"{self.wrapper.getName()}")

    def canFetchMore(self) -> bool:
        if self._has_fetched or not self.hasChildren():
            return False
        return self.wrapper.countChildren() > 0

    def fetchChildren(self):
        for child in self.wrapper.listChildren():
            self.appendRow(OMEROTreeItem(child))
        self._has_fetched = True

    def hasChildren(self):
        return bool(self.wrapper.CHILD_WRAPPER_CLASS)

    def numChildren(self) -> int:
        return self.wrapper.countChildren()

    def isDataset(self) -> bool:
        return isinstance(self.wrapper, _DatasetWrapper)

    def isImage(self) -> bool:
        return isinstance(self.wrapper, _ImageWrapper)


class OMEROTreeModel(QStandardItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conn: BlitzGateway = None

    def _populate_tree(self):
        root = self.invisibleRootItem()
        projects = []
        for project in self.conn.listProjects():
            item = OMEROTreeItem(project)
            root.appendRow(item)
            projects.append(item)
            yield

        for item in projects:
            for dataset in item.wrapper.listChildren():
                dchild = OMEROTreeItem(dataset)
                item.appendRow(dchild)
                yield
                for image in dataset.listChildren():
                    ichild = OMEROTreeItem(image)
                    dchild.appendRow(ichild)
                    yield

    def set_connection(self, conn: BlitzGateway, parent=None):
        self.conn = conn
        create_worker(self._populate_tree, _start_thread=True)

    # def canFetchMore(self, index: QModelIndex) -> bool:
    #     item = self.itemFromIndex(index)
    #     return bool(item and item.canFetchMore())

    # def fetchMore(self, index: QModelIndex) -> None:
    #     self.itemFromIndex(index).fetchChildren()

    def hasChildren(self, index: QModelIndex) -> bool:
        item = self.itemFromIndex(index)
        if item is not None:
            return item.hasChildren() and item.numChildren() > 0
        return True

    def itemFromIndex(self, index: QModelIndex) -> OMEROTreeItem:
        return super().itemFromIndex(index)
