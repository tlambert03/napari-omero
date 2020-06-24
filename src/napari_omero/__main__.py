from napari import gui_qt, Viewer  # type: ignore  # getting no attribute err
from qtpy.QtCore import Qt

from .widgets import OMEROWidget


def main():
    with gui_qt():
        viewer = Viewer()
        m = OMEROWidget()
        dw = viewer.window.add_dock_widget(m, area="right")
        # TODO: figure out dynamic geometry
        viewer.window._qt_window.setGeometry(300, 200, 1280, 720)
        viewer.window._qt_window.resizeDocks([dw], [390], Qt.Horizontal)


if __name__ == '__main__':
    import sys

    sys.exit(main())
