import napari
from qtpy.QtCore import Qt

from napari_omero.widgets.main import OMEROWidget

with napari.gui_qt():
    viewer = napari.Viewer()
    m = OMEROWidget()
    dw = viewer.window.add_dock_widget(m, area="right")
    viewer.window._qt_window.setGeometry(300, 200, 1280, 720)
    viewer.window._qt_window.resizeDocks([dw], [390], Qt.Horizontal)