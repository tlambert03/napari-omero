from setuptools import setup


with open("README.rst", "r") as fh:
    long_description = fh.read()

setup(
    name="omero-napari",
    version="0.1.0",
    description="OMERO/napari interoperability",
    long_description=long_description,
    author="The Open Microscopy and napari teams",
    packages=["omero_napari", "omero.plugins"],
    package_dir={"": "src"},
    install_requires=["napari[all]>=0.3.0", "omero-py"],
    keywords=["OMERO.CLI", "plugin", "napari"],
    entry_points={"napari.plugin": ["omero = napari_omero.plugin"]},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Plugins",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
