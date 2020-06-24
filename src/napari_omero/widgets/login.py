import os

from qtpy.QtGui import QIntValidator
from qtpy.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    QVBoxLayout,
)
from .gateway import QGateWay


class LoginForm(QDialog):
    def __init__(self, gateway: QGateWay, parent=None):
        super().__init__(parent)
        self.gateway = gateway
        self.setup_ui()
        self.gateway.status.connect(self.status.setText)
        self.gateway.error.connect(self._on_gateway_error)
        self.gateway.connected.connect(self.hide)
        self.gateway.try_restore_session()

    def setup_ui(self):
        self.host = QLineEdit(self)
        self.host.setMinimumWidth(170)
        self.port = QLineEdit(self)
        self.port.setValidator(QIntValidator(0, 99999, self))
        self.username = QLineEdit(self)
        self.password = QLineEdit(self)
        self.password.setEchoMode(QLineEdit.Password)
        self.password.editingFinished.connect(
            lambda: [self._connect() if self.password.text() else None]
        )

        host, user, uuid, port = self.gateway.get_current()
        self.host.setText(self.gateway._host or host or "")
        self.port.setText(self.gateway._port or port or "")
        self.username.setText(self.gateway._user or user or "")
        self.password.setText(os.getenv("OMERO_PASSWORD"))
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.connect_btn = QPushButton("connect", self)
        self.connect_btn.clicked.connect(self._connect)

        self.login_form = QWidget(self)
        login_layout = QGridLayout(self.login_form)
        login_layout.setContentsMargins(0, 0, 0, 0)
        login_layout.addWidget(QLabel("host", self), 0, 0)
        login_layout.addWidget(self.host, 0, 1)
        login_layout.addWidget(QLabel("port", self), 1, 0)
        login_layout.addWidget(self.port, 1, 1)
        login_layout.addWidget(QLabel("username", self), 2, 0)
        login_layout.addWidget(self.username, 2, 1)
        login_layout.addWidget(QLabel("password", self), 3, 0)
        login_layout.addWidget(self.password, 3, 1)
        login_layout.addWidget(self.connect_btn, 4, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.login_form)
        layout.addWidget(self.status)

    def _connect(self):
        self.gateway.create_session(
            self.host.text(),
            self.port.text(),
            self.username.text(),
            self.password.text(),
        )

    def _on_gateway_error(self, err):
        self.status.setText(str(err))
