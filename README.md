# napari-omero

This is an OMERO plugin and gui interface for napari:

![demo](demo.gif)

Data loading mechanisms inspired by [`omero-napari`](https://gitlab.com/openmicroscopy/incubator/omero-napari)

Also provides a napari reader plugin that accepts two omero resource formats:

```python
viewer = napari.Viewer()
viewer.open("Image:1", plugin="omero")  # omero object identifier

# or URLS: https://help.openmicroscopy.org/urls-to-data.html
viewer.open("http://yourdomain.example.org/omero/webclient/?show=image-314")
```

these will also work on the napari command line interface, e.g.:

```shell
napari Image:1
# or
napari http://yourdomain.example.org/omero/webclient/?show=image-314
```

## installation

This is experimental and not yet published on PyPI.
Requires python 3.6 due to `omero-py` Ice dependencies.  First install `omero-py`:

```sh
conda create -n omero -c ome python=3.6 zeroc-ice36-python omero-py
conda activate omero
# then install this repo from github
pip install git+git://github.com/tlambert03/napari-omero
```

## usage

launch the main interface with

```sh
python -m napari_omero
```

## issues

- totally experimental & still quite buggy!
- remote loading can be very slow still... though this is not really an issue of this plugin.  Datasets are wrapped as delayed dask stacks, and remote data fetching time can be significant.  Plans for [asynchronous rendering](https://napari.org/docs/explanations/rendering.html) may eventually improve the subjective performance... but remote data loading will likely always be a limitation here.
