# napari-omero

[![License](https://img.shields.io/pypi/l/napari-omero.svg?color=green)](https://github.com/tlambert03/napari-omero/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/napari-omero.svg?color=green)](https://pypi.org/project/napari-omero)
[![Python Version](https://img.shields.io/pypi/pyversions/napari-omero.svg?color=green)](https://python.org)
[![CI](https://github.com/tlambert03/napari-omero/actions/workflows/ci.yml/badge.svg)](https://github.com/tlambert03/napari-omero/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/tlambert03/napari-omero/branch/main/graph/badge.svg)](https://codecov.io/gh/tlambert03/napari-omero)
[![conda-forge](https://img.shields.io/conda/vn/conda-forge/napari-omero)](https://anaconda.org/conda-forge/napari-omero)

This package provides interoperability between the
[OMERO](https://www.openmicroscopy.org/omero/) image management platform, and
[napari](https://github.com/napari/napari): a fast, multi-dimensional image
viewer for python.

It provides a GUI interface for browsing an OMERO instance from within napari,
as well as command line interface extensions for both OMERO and napari CLIs.

![demo](https://github.com/tlambert03/napari-omero/blob/master/demo.gif?raw=true)

## Features

- GUI interface to browse remote OMERO data, with thumbnail previews.
- Loads remote nD images from an OMERO server into napari
- Planes are loading on demand as sliders are moved ("lazy loading").
- session management (login memory)
- OMERO rendering settings (contrast limits, colormaps, active channels, current
  Z/T position) are applied in napari

### as a napari dock widget

To launch napari with the OMERO browser added, [install](#installation) this
package and run:

```bash
napari-omero
```

The OMERO browser widget can also be manually added to the napari viewer:

```python
import napari

viewer = napari.Viewer()
viewer.window.add_plugin_dock_widget('napari-omero')

napari.run()
```

### as a napari plugin

This package provides a napari reader plugin that accepts OMERO resources as
"proxy strings" (e.g. `omero://Image:<ID>`) or as [OMERO webclient
URLS](https://help.openmicroscopy.org/urls-to-data.html).

```python
viewer = napari.Viewer()

# omero object identifier string
viewer.open("omero://Image:1")

# or URLS: https://help.openmicroscopy.org/urls-to-data.html
viewer.open("http://yourdomain.example.org/omero/webclient/?show=image-314")
```

these will also work on the napari command line interface, e.g.:

```bash
napari omero://Image:1
# or
napari http://yourdomain.example.org/omero/webclient/?show=image-314
```

### as an OMERO CLI plugin

This package also serves as a plugin to the OMERO CLI

```bash
omero napari view Image:1
```

- ROIs created in napari can be saved back to OMERO via a "Save ROIs" button.
- napari viewer console has BlitzGateway 'conn' and 'omero_image' in context.

## installation

While this package supports anything above python 3.9,
In practice, python support is limited by `omero-py` and `zeroc-ice`,
compatibility, which is limited to python <=3.10 at the time of writing.

### from conda

It's easiest to install `omero-py` from conda, so the recommended procedure
is to install everything from conda, using the `conda-forge` channel

```sh
conda install -c conda-forge napari-omero
```

### from pip

`napari-omero` itself can be installed from pip, but you will still need
`omero-py`

```sh
conda create -n omero -c conda-forge python=3.10 omero-py
conda activate omero
pip install napari-omero[all]  # the [all] here is the same as `napari[all]`
```

## issues

| ❗  | This is alpha software & some things will be broken or sub-optimal!  |
| --- | -------------------------------------------------------------------- |

- experimental & definitely still buggy!  [Bug
  reports](https://github.com/tlambert03/napari-omero/issues/new) are welcome!
- remote loading can be very slow still... though this is not strictly an issue
  of this plugin.  Datasets are wrapped as delayed dask stacks, and remote data
  fetching time can be significant.  Plans for [asynchronous
  rendering](https://napari.org/guides/stable/rendering.html) in
  napari and
  [tiled loading from OMERO](https://github.com/tlambert03/napari-omero/pull/1)
  may eventually improve the subjective performance... but remote data loading
  will likely always be a limitation here.
  To try asyncronous loading, start the program with `NAPARI_ASYNC=1 napari-omero`.

## contributing

Contributions are welcome!  To get setup with a development environment:

```bash
# clone this repo:
git clone https://github.com/tlambert03/napari-omero.git
# change into the new directory
cd napari-omero
# create conda environment
conda env create -n napari-omero python=3.10 omero-py
# activate the new env
conda activate napari-omero

# install in editable mode with dev dependencies
pip install -e ".[dev]"      # quotes are needed on zsh
```

To maintain good code quality, this repo uses
[ruff](https://github.com/astral-sh/ruff),
[mypy](https://github.com/python/mypy).

To enforce code quality when you commit code, you can install pre-commit

```bash
# install pre-commit which will run code checks prior to commits
pre-commit install
```

The original OMERO data loader and CLI extension was created by [Will
Moore](https://github.com/will-moore).

The napari reader plugin and GUI browser was created by [Talley
Lambert](https://github.com/tlambert03/)

## release

To psuh a release to PyPI, one of the maintainers needs to do, for example:
```sh
git tag -a v0.2.0 -m v0.2.0
git push upstream --follow-tags
```
Then, the workflow should handle everything!
