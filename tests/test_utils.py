from napari_omero.utils import parse_omero_url


def test_parse_omero_url():
    url = 'http://yourdomain.example.org/omero/webclient/?show=dataset-314'
    match = parse_omero_url(url)
    assert match == {
        'host': 'yourdomain.example.org',
        'type': 'dataset',
        'id': '314',
    }
