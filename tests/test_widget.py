from unittest.mock import patch

from napari_omero import OMEROWidget


def test_widget(make_napari_viewer):
    from napari_omero.widgets.gateway import QGateWay

    viewer = make_napari_viewer()
    with patch.object(QGateWay, '_try_restore_session', lambda x: None):
        widget = OMEROWidget()
        viewer.window.add_dock_widget(widget)
