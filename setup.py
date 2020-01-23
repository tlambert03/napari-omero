
from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='omero-napari',
    version='0.0.3dev',
    description="OMERO CLI plugin to view images in napari",
    long_description=long_description,
    author="The Open Microscopy Team",
    packages=['', 'omero.plugins'],
    package_dir={"": "src"},
    install_requires=['napari>=0.2.10'],
    keywords=['OMERO.CLI', 'plugin', 'napari'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Plugins',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v2 '
        'or later (GPLv2+)',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],  # Get strings from
        # http://pypi.python.org/pypi?%3Aaction=list_classifiers
)
