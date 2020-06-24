# napari-omero

This package provides interoperability between the
[OMERO](https://www.openmicroscopy.org/omero/) image management platform, and
[napari](https://github.com/napari/napari): a fast, multi-dimensional image
viewer for python.

It provides a GUI interface for browsing an OMERO instance from within napari,
as well as command line interface extensions for both OMERO and napari CLIs.

![demo](demo.gif)

## Features

- GUI interface to browse remote OMERO data, with thumbnail previews.
- Loads remote nD images from an OMERO server into napari
- Planes are loading on demand as sliders are moved ("lazy loading").
- session management (login memory)
- OMERO rendering settings (contrast limits, colormaps, active channels, current
  Z/T position) are applied in napari

### as a napari plugin

This package provides a napari reader plugin that accepts OMERO resources as
"proxy strings" (`Image:<ID>`) or as [OMERO webclient
URLS](https://help.openmicroscopy.org/urls-to-data.html).

```python
viewer = napari.Viewer()

# omero object identifier string
viewer.open("Image:1", plugin="omero")

# or URLS: https://help.openmicroscopy.org/urls-to-data.html
viewer.open("http://yourdomain.example.org/omero/webclient/?show=image-314")
```

these will also work on the napari command line interface, e.g.:

```bash
napari Image:1
# or
napari http://yourdomain.example.org/omero/webclient/?show=image-314
```

### as a napari dock widget

The main OMERO browser widget can be manually added to the napari viewer:

```python
import napari
from napari_omero import OMEROWidget

with napari.gui_qt():
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(OMEROWidget(), area="right")
```

Or, to launch napari with this widget added automatically, run:

```bash
napari_omero
```

### as an OMERO CLI plugin

This package also serves as a plugin to the OMERO CLI

```bash
omero napari view Image:1
```

- ROIs created in napari can be saved back to OMERO via a "Save ROIs" button.
- napari viewer console has BlitzGateway 'conn' and 'omero_image' in context.

## installation

Requires python 3.6 or 3.7 due to `omero-py` Ice dependencies.  First install
`omero-py`:

```sh
conda create -n omero -c ome python=3.7 omero-py
conda activate omero

# then install this repo from github
pip install git+git://github.com/tlambert03/napari-omero
```

## issues

- experimental & definitely still buggy!  Feel free to report issues.
- remote loading can be very slow still... though this is not really an issue of
  this plugin.  Datasets are wrapped as delayed dask stacks, and remote data
  fetching time can be significant.  Plans for [asynchronous
  rendering](https://napari.org/docs/explanations/rendering.html) may eventually
  improve the subjective performance... but remote data loading will likely
  always be a limitation here.

## contributions

Contributions are welcome.  Please submit a PR.

The original OMERO data loader and CLI extension was created by [Will
Moore](https://github.com/will-moore).

The napari reader plugin and GUI browser was created by [Talley
Lambert](https://github.com/tlambert03/)