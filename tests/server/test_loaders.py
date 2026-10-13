import numpy as np
import pytest

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


def test_load_plane_after_group_switch(conn, image_id, image_array):
    """Planes of an open image still load after the browser switches group.

    Regression test: plane stores were opened with the connection's shared
    SERVICE_OPTS, which the browser's group combo changes. Every plane not yet
    loaded then failed with "Cannot read pixels".
    """
    image = conn.getObject("Image", image_id)
    [(data, _meta, _layer_type)] = load_image_wrapper(image)

    image_group = image.getDetails().getGroup().getId()
    other_groups = [
        g for g in conn.getEventContext().memberOfGroups if g != image_group
    ]
    if not other_groups:
        pytest.skip("test user is in only one group")

    previous = conn.SERVICE_OPTS.getOmeroGroup()
    conn.SERVICE_OPTS.setOmeroGroup(other_groups[0])  # what the group combo does
    try:
        plane = np.asarray(data[0, 0, 0])  # first fetch of this plane
    finally:
        conn.SERVICE_OPTS.setOmeroGroup(previous)

    np.testing.assert_array_equal(plane, image_array[:, :, 0, 0, 0].T)
