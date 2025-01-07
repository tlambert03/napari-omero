import itertools
from typing import Any, Optional

from qtpy.QtCore import QModelIndex, Qt
from qtpy.QtGui import QStandardItem, QStandardItemModel

from omero.gateway import BlitzObjectWrapper, _DatasetWrapper, _ImageWrapper

from .gateway import QGateWay

_ICON_MAP = {
    "Project": "🗃",
    "Dataset": "📁",
}


class OMEROTreeItem(QStandardItem):
    def __init__(self, wrapper: BlitzObjectWrapper):
        super().__init__()
        self.wrapper = wrapper
        self._has_fetched = False
        if self.child_type:
            self.setText(f"{self.wrapper.getName()} ({self.n_children})")
        else:
            self.setText(f"{self.wrapper.getName()}")

    def data(self, role: int = 0) -> Any:
        d = super().data(role)
        if role == Qt.ItemDataRole.DisplayRole:
            d = _ICON_MAP.get(self.wrapper_type, "") + d
        return d

    def canFetchMore(self) -> bool:
        return not self._has_fetched and self.hasChildren()

    def yieldChildren(self):
        yield from self.wrapper._conn.getObjects(
            self.child_type,
            opts={
                self.wrapper_type.lower(): self.wrapper.id,
                "order_by": "obj.name",
            },
        )

    def hasChildren(self) -> bool:
        return bool(self.child_type and self.n_children > 0)

    @property
    def child_type(self) -> Optional[str]:
        kls = self.wrapper.CHILD_WRAPPER_CLASS or ""
        kls = kls if isinstance(kls, str) else kls.__name__
        return kls.lstrip("_").replace("Wrapper", "") if kls else None

    @property
    def wrapper_type(self) -> str:
        return self.wrapper.OMERO_CLASS

    @property
    def parent_type(self) -> Optional[str]:
        kls = self.wrapper.PARENT_WRAPPER_CLASS or ""
        kls = kls if isinstance(kls, str) else kls.__name__
        return kls.lstrip("_").replace("Wrapper", "") if kls else None

    @property
    def n_children(self) -> int:
        if not hasattr(self, "_n_children"):
            self._n_children = self.wrapper.countChildren()
        return self._n_children

    def isDataset(self) -> bool:
        return isinstance(self.wrapper, _DatasetWrapper)

    def isImage(self) -> bool:
        return isinstance(self.wrapper, _ImageWrapper)


class OMEROTreeModel(QStandardItemModel):
    def __init__(self, gateway: QGateWay, parent=None):
        super().__init__(parent)
        self.gateway = gateway
        self._wrapper_map: dict[BlitzObjectWrapper, QModelIndex] = {}

    def submit_get_projects(self, *_, owner=None, group=None):
        root = self.invisibleRootItem()
        while root.rowCount() > 0:
            root.removeRow(0)
        root.appendRow(QStandardItem("loading..."))
        self.gateway._submit(
            self._get_projects,
            owner=owner,
            group=group,
            _connect={"returned": self._add_projects},
        )

    def _get_projects(self, owner=None, group=None):
        opts = {"order_by": "obj.name"}
        if owner is not None:
            opts["owner"] = owner
        if group is None:
            group = -1
        self.gateway.conn.SERVICE_OPTS.setOmeroGroup(group)
        return itertools.chain(
            self.gateway.getObjects("Project", opts=opts),
            self.gateway.getObjects("Dataset", opts={**opts, "orphaned": True}),
        )

    def _add_projects(self, projects):
        root = self.invisibleRootItem()
        while root.rowCount() > 0:
            root.removeRow(0)
        projects = list(projects)
        for project in projects:
            item = OMEROTreeItem(project)
            root.appendRow(item)
            self._wrapper_map[project.getId()] = self.indexFromItem(item)

    def canFetchMore(self, index: QModelIndex) -> bool:
        item = self.itemFromIndex(index)
        return bool(item and item.canFetchMore())

    def fetchMore(self, index: QModelIndex) -> None:
        item = self.itemFromIndex(index)
        for child in item.yieldChildren():
            child_item = OMEROTreeItem(child)
            item.appendRow(child_item)
            self._wrapper_map[child.getId()] = self.indexFromItem(child_item)
        item._has_fetched = True

    def hasChildren(self, index: QModelIndex) -> bool:
        item = self.itemFromIndex(index)
        if item is not None:
            return item.hasChildren() and item.n_children > 0
        return True

    def itemFromIndex(self, index: QModelIndex) -> OMEROTreeItem:
        return super().itemFromIndex(index)
