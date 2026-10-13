import numpy as np

from napari_omero.plugins.loaders import load_image_wrapper


def test_load_image(conn, image_id, image_array):
    """The loader returns the image's pixels as one TCZYX array, split by channel."""
    image = conn.getObject("Image", image_id)

    [(data, meta, layer_type)] = load_image_wrapper(image)

    assert layer_type == "image"
    assert meta["channel_axis"] == 1
    expected = image_array.transpose(4, 3, 2, 1, 0)  # XYZCT -> TCZYX
    assert data.shape == expected.shape
    assert data.dtype == expected.dtype
    np.testing.assert_array_equal(np.asarray(data), expected)
