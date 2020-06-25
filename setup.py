from setuptools import setup, find_packages

setup(
    package_dir={"": "src"},
    packages=find_packages("src") + ['omero.plugins'],
    use_scm_version={"write_to": "src/napari_omero/_version.py"},
    setup_requires=["setuptools_scm"],
)
