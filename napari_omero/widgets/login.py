import os

from napari.qt import create_worker
from omero.gateway import BlitzGateway
from omero.util.sessions import SessionsStore
from qtpy.QtCore import Signal
from qtpy.QtGui import QIntValidator
from qtpy.QtWidgets import QDialog, QGridLayout, QLabel, QLineEdit, QPushButton


class LoginForm(QDialog):
    connected = Signal(BlitzGateway)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.conn = None
        self.setup_ui()
        self.store = SessionsStore()

        worker = create_worker(self._try_restore_session)
        worker.returned.connect(self._on_new_session)
        worker.errored.connect(self._on_session_error)
        worker.start()

    def _try_restore_session(self):
        self.status.setText("connecting...")
        server, name, uuid, port = self.store.get_current()
        self.host.setText(server or "")
        self.port.setText(port or "")
        self.username.setText(name or "")
        if uuid and self.store.exists(server, name, uuid):
            return self.store.attach(server, name, uuid)
        return False

    def setup_ui(self):
        layout = QGridLayout(self)
        self.host = QLineEdit(self)
        self.host.setMinimumWidth(170)
        self.port = QLineEdit(self)
        self.port.setValidator(QIntValidator(0, 99999, self))
        self.username = QLineEdit(self)
        self.password = QLineEdit(self)
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setText(os.getenv("OMERO_PASSWORD"))
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        connect_btn = QPushButton("connect", self)
        connect_btn.clicked.connect(self._connect)

        layout.addWidget(QLabel("host", self), 0, 0)
        layout.addWidget(self.host, 0, 1)
        layout.addWidget(QLabel("port", self), 1, 0)
        layout.addWidget(self.port, 1, 1)
        layout.addWidget(QLabel("username", self), 2, 0)
        layout.addWidget(self.username, 2, 1)
        layout.addWidget(QLabel("password", self), 3, 0)
        layout.addWidget(self.password, 3, 1)
        layout.addWidget(connect_btn, 4, 0, 1, 2)
        layout.addWidget(self.status, 5, 0, 1, 2)

    def _connect(self):
        self.status.setText("connecting...")
        self._try_connect()

    def _on_new_session(self, result):
        self.status.setText("")
        if not result:
            return
        client, uuid, idle, live = result
        self.conn = BlitzGateway(client_obj=client)
        self.connected.emit(self.conn)

    def _on_session_error(self, err):
        self.status.setText(getattr(err, "reason", ""))

    def _try_connect(self):
        props = {
            "omero.host": self.host.text(),
            "omero.port": self.port.text(),
            "omero.user": self.username.text(),
            "omero.timeout": 20 * 60,
        }
        self._ = create_worker(
            self.store.create,
            self.username.text(),
            self.password.text(),
            props,
            _connect={
                "returned": self._on_new_session,
                "errored": self._on_session_error,
            },
            _start_thread=True,
        )

    def close(self):
        if self.conn:
            self.conn.close()
