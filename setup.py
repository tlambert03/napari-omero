from setuptools import setup, find_packages

setup(
    name="napari-omero",
    description="An OMERO gui for napari",
    author="Talley Lambert",
    author_email="talley.lambert@gmail.com",
    packages=find_packages(),
    version="0.1.0",
    entry_points={"napari.plugin": ["omero = napari_omero.plugin"]},
    install_requires=['omero-py', 'napari']
)
