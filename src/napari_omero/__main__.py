def main():
    import napari
    from qtpy.QtCore import Qt

    viewer = napari.Viewer()  # type: ignore
    dw, _ = viewer.window.add_plugin_dock_widget("napari-omero", "OMERO Browser")
    # TODO: figure out dynamic geometry
    viewer.window._qt_window.resizeDocks([dw], [390], Qt.Orientation.Horizontal)
    napari.run()  # type: ignore


if __name__ == "__main__":
    import sys

    sys.exit(main())
