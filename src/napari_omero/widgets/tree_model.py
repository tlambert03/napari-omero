from omero.gateway import (
    BlitzObjectWrapper,
    _DatasetWrapper,
    _ImageWrapper,
)
from qtpy.QtCore import QModelIndex
from qtpy.QtGui import QStandardItem, QStandardItemModel
from .gateway import QGateWay
from typing import Dict


class OMEROTreeItem(QStandardItem):
    def __init__(self, wrapper: BlitzObjectWrapper):
        super().__init__()
        self.wrapper = wrapper
        self.setData(wrapper)
        # self._has_fetched = False
        if self.hasChildren():
            self.setText(f"{self.wrapper.getName()} ({self.numChildren()})")
        else:
            self.setText(f"{self.wrapper.getName()}")

    # def canFetchMore(self) -> bool:
    #     if self._has_fetched or not self.hasChildren():
    #         return False
    #     return self.wrapper.countChildren() > 0

    # def fetchChildren(self):
    #     for child in self.wrapper.listChildren():
    #         self.appendRow(OMEROTreeItem(child))
    #     self._has_fetched = True

    def hasChildren(self):
        return bool(self.wrapper.CHILD_WRAPPER_CLASS)

    def numChildren(self) -> int:
        return self.wrapper.countChildren()

    def isDataset(self) -> bool:
        return isinstance(self.wrapper, _DatasetWrapper)

    def isImage(self) -> bool:
        return isinstance(self.wrapper, _ImageWrapper)


class OMEROTreeModel(QStandardItemModel):
    def __init__(self, gateway: QGateWay, parent=None):
        super().__init__(parent)
        self.gateway = gateway
        self.gateway.connected.connect(
            lambda g: self.gateway._submit(self._populate_tree)
        )
        self._wrapper_map: Dict[BlitzObjectWrapper, QModelIndex] = {}

    def _populate_tree(self):
        if not self.gateway.isConnected():
            return

        root = self.invisibleRootItem()
        projects = []
        for project in list(self.gateway.conn.listProjects()):
            item = OMEROTreeItem(project)
            root.appendRow(item)
            projects.append(item)
            self._wrapper_map[project.getId()] = self.indexFromItem(item)
            yield

        if not self.gateway.isConnected():
            return

        for item in projects:
            for dataset in list(item.wrapper.listChildren()):
                dchild = OMEROTreeItem(dataset)
                item.appendRow(dchild)
                self._wrapper_map[dataset.getId()] = self.indexFromItem(dchild)

                yield
                if not self.gateway.isConnected():
                    return
                for image in list(dataset.listChildren()):
                    ichild = OMEROTreeItem(image)
                    dchild.appendRow(ichild)
                    self._wrapper_map[image.getId()] = self.indexFromItem(
                        ichild
                    )
                    yield

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
