def test_server_connection(conn):
    """
    Tests that a connection can be made to the OMERO server.
    """
    assert conn.isConnected()


def test_omero_browser_login(make_napari_viewer, omero_params, qtbot):
    from napari_omero import OMEROWidget

    user, password, host, web_host, port, secure = omero_params

    viewer = make_napari_viewer()
    widget = OMEROWidget()
    viewer.window.add_dock_widget(widget)

    # Wait for the 'connected' signal to be emitted
    with qtbot.waitSignal(widget.gateway.connected, timeout=10000):
        widget.gateway.create_session(
            host=host, port=port, username=user, password=password
        )

    assert widget.gateway.conn is not None
    assert widget.gateway.conn.isConnected()
