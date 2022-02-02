import napari
from qtpy.QtCore import Qt

from .widgets import OMEROWidget


def main():

    viewer = napari.Viewer()
    m = OMEROWidget()
    dw = viewer.window.add_dock_widget(m, area="right")
    # TODO: figure out dynamic geometry
    viewer.window._qt_window.setGeometry(300, 200, 1280, 720)
    viewer.window._qt_window.resizeDocks([dw], [390], Qt.Horizontal)
    napari.run()


if __name__ == '__main__':
    import sys

    sys.exit(main())
