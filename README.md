# omero-napari

OMERO CLI client to open images in the napari viewer


Requires Python 3.6 or higher and install https://github.com/ome/omero-py to
connect to OMERO.

Install conda from https://docs.conda.io/en/latest/miniconda.html, then::

    # Create a conda environment named 'napari' and install omero-py

    conda create -n napari -c ome python=3.6 zeroc-ice36-python omero-py
    conda activate napari

    # Install napari and omero-napari

    pip install "napari>=0.2.10"
    pip install -i https://test.pypi.org/simple/ omero-napari

    # View an image in OMERO (will prompt for server and login)

    omero napari view Image:1

    # By default we lazy-load planes as needed. To load all planes:

    omero napari view Image:1 --eager


Features
========

 - Loads planes from OMERO as 2D numpy arrays and opens the image in napari.
 - Z and T dimensions from OMERO are supported with Z and T sliders in napari.
 - Only the required planes are loaded ("lazy loading"). Additional planes are
   loaded when the Z/T sliders are changed.
 - All channels from OMERO are shown in napari.
 - Rendering settings from OMERO are applied to napari so it looks the same:
     - The range and settings of the contrast sliders.
     - The color of each channel.
     - Only active layers are loaded and visible in napari.
     - The Z/T sliders are set to the default Z/T index from OMERO.
 - ROIs created in napari can be saved back to OMERO via a "Save ROIs" button.
