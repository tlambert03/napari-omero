import atexit
from typing import Callable, Optional, Tuple, Generator

from napari.qt.threading import WorkerBase, create_worker
from omero.clients import BaseClient
from omero.gateway import BlitzGateway, PixelsWrapper, BlitzObjectWrapper
import omero.gateway
from omero.util.sessions import SessionsStore
from qtpy.QtCore import QObject, Signal

SessionStats = Tuple[BaseClient, str, int, int]


class QGateWay(QObject):
    status = Signal(str)
    connected = Signal(BlitzGateway)
    disconnected = Signal()
    error = Signal(object)

    # singletons
    _conn: Optional[BlitzGateway] = None
    _host: Optional[str] = None
    _port: Optional[str] = None
    _user: Optional[str] = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store = SessionsStore()
        self.destroyed.connect(self.close)
        atexit.register(self.close)
        self.worker: Optional[WorkerBase] = None
        self._next_worker: Optional[WorkerBase] = None

    @property
    def conn(self):
        return QGateWay._conn

    @conn.setter
    def conn(self, val):
        QGateWay._conn = val

    @property
    def host(self):
        return QGateWay._host

    @host.setter
    def host(self, val):
        QGateWay._host = val

    @property
    def port(self):
        return QGateWay._port

    @port.setter
    def port(self, val):
        QGateWay._port = val

    @property
    def user(self):
        return QGateWay._user

    @user.setter
    def user(self, val):
        QGateWay._user = val

    def isConnected(self):
        return self.conn and self.conn.isConnected()

    def close(self, hard=False):
        if self.isConnected():
            self.conn.close(hard=hard)
            try:
                self.disconnected.emit()
            except RuntimeError:
                # if called during atexit the C/C++ object may be deleted
                pass

    def connect(self):
        if not self.conn:
            raise ValueError("No gateway to connect")
        if not self.conn.isConnected():
            if not self.conn.c:
                self.conn._resetOmeroClient()
            if self.conn.connect():
                self.connected.emit(self.conn)

    def get_current(self) -> Tuple[str, str, str, str]:
        return self.store.get_current()

    def _start_next_worker(self):
        if self._next_worker is not None:
            self.worker = self._next_worker
            self._next_worker = None
            self.worker.start()
        else:
            self.worker = None

    def _submit(
        self, func: Callable, *args, _wait=True, **kwargs
    ) -> WorkerBase:
        new_worker = create_worker(func, *args, _start_thread=False, **kwargs)
        new_worker.finished.connect(self._start_next_worker)

        if self.worker and self.worker.is_running:
            self._next_worker = new_worker
            if not _wait:
                self.worker.quit()
        else:
            self.worker = new_worker
            self.worker.start()
        return new_worker

    def try_restore_session(self):
        return self._submit(self._try_restore_session)

    def _try_restore_session(self) -> Optional[SessionStats]:
        host, username, uuid, port = self.get_current()
        host = self.host or host
        username = self.user or username
        port = self.port or port
        if uuid and self.store.exists(host, username, uuid):
            try:
                self.status.emit("connecting...")
                session = self.store.attach(host, username, uuid)
                return self._on_new_session(session)
            except Exception as e:
                self.status.emit("Error")
                self.error.emit(e)
        return None

    def create_session(
        self, host: str, port: str, username: str, password: str
    ):
        return self._submit(
            self._create_session, host, port, username, password
        )

    def _create_session(
        self, host: str, port: str, username: str, password: str
    ):
        self.status.emit("connecting...")
        try:
            props = {
                "omero.host": host,
                "omero.user": username,
            }
            if port:
                props['omero.port'] = port
            session = self.store.create(username, password, props)
            return self._on_new_session(session)
        except Exception as e:
            self.status.emit("Error")
            self.error.emit(e)

    def _on_new_session(self, session: SessionStats):
        client = session[0]
        if not client:
            return
        self.conn = BlitzGateway(client_obj=client)
        self.host = client.getProperty("omero.host")
        self.port = client.getProperty("omero.port")
        self.user = client.getProperty("omero.user")

        self.connected.emit(self.conn)
        self.status.emit("")
        return self.conn

    def getObjects(
        self, name: str, **kwargs
    ) -> Generator[BlitzObjectWrapper, None, None]:
        if not self.isConnected():
            raise RuntimeError("No connection!")
        yield from self.conn.getObjects(name, **kwargs)


class NonCachedPixelsWrapper(PixelsWrapper):
    """Extend gateway.PixelWrapper to override _prepareRawPixelsStore."""

    def _prepareRawPixelsStore(self):
        """
        Creates RawPixelsStore and sets the id etc

        This overrides the superclass behaviour to make sure that
        we don't re-use RawPixelStore in multiple processes since
        the Store may be closed in 1 process while still needed elsewhere.
        This is needed when napari requests may planes simultaneously,
        e.g. when switching to 3D view.
        """
        ps = self._conn.c.sf.createRawPixelsStore()
        ps.setPixelsId(self._obj.id.val, True, self._conn.SERVICE_OPTS)
        return ps


omero.gateway.PixelsWrapper = NonCachedPixelsWrapper
# Update the BlitzGateway to use our NonCachedPixelsWrapper
omero.gateway.refreshWrappers()
