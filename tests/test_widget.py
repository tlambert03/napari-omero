from unittest.mock import patch


def test_browser_widget(make_napari_viewer):
    from napari_omero.widgets.gateway import QGateWay

    viewer = make_napari_viewer()
    with patch.object(QGateWay, "_try_restore_session", lambda x: None):
        viewer.window.add_plugin_dock_widget("napari-omero", "OMERO Browser")
