from functools import wraps

import omero.clients  # noqa
from omero.rtypes import rdouble, rint
from omero.model import PointI, ImageI, RoiI
from omero.gateway import BlitzGateway

from vispy.color import Colormap
import napari
from dask import delayed
import dask.array as da

import numpy

import sys
from omero.cli import CLI
from omero.cli import BaseControl
from omero.cli import ProxyStringType

HELP = "Connect OMERO to the napari image viewer"

VIEW_HELP = "Usage: omero napari view Image:1"


def gateway_required(func):
    """
    Decorator which initializes a client (self.client),
    a BlitzGateway (self.gateway), and makes sure that
    all services of the Blitzgateway are closed again.
    """

    @wraps(func)
    def _wrapper(self, *args, **kwargs):
        self.client = self.ctx.conn(*args)
        self.gateway = BlitzGateway(client_obj=self.client)

        try:
            return func(self, *args, **kwargs)
        finally:
            if self.gateway is not None:
                self.gateway.close(hard=False)
                self.gateway = None
                self.client = None

    return _wrapper


class NapariControl(BaseControl):

    gateway = None
    client = None

    def _configure(self, parser):
        parser.add_login_arguments()
        sub = parser.sub()
        view = parser.add(sub, self.view, VIEW_HELP)

        obj_type = ProxyStringType("Image")

        view.add_argument("object", type=obj_type, help="Object to view")
        view.add_argument(
            "--eager",
            action="store_true",
            help=(
                "Use eager loading to load all planes immediately instead"
                "of lazy-loading each plane when needed"
            ),
        )

    @gateway_required
    def view(self, args):

        if isinstance(args.object, ImageI):
            img = self._lookup(self.gateway, "Image", args.object.id)
            self.ctx.out("View image: %s" % img.name)

            with napari.gui_qt():
                viewer = napari.Viewer()
                load_omero_image(viewer, img, eager=args.eager)

    def _lookup(self, gateway, type, oid):
        """Find object of type by ID."""
        gateway.SERVICE_OPTS.setOmeroGroup("-1")
        obj = gateway.getObject(type, oid)
        if not obj:
            self.ctx.die(110, "No such %s: %s" % (type, oid))
        return obj


def load_omero_image(viewer, image, eager=False):
    """
    Entry point - can be called to initially load an image
    from OMERO into the napari viewer

    :param  viewer:     napari viewer instance
    :param  image:      omero.gateway.ImageWrapper
    :param  eager:      If true, load all planes immediately
    """
    for c, channel in enumerate(image.getChannels()):
        print("loading channel %s:" % c)
        load_omero_channel(viewer, image, channel, c, eager)

    set_dims_defaults(viewer, image)
    set_dims_labels(viewer, image)


def load_omero_channel(viewer, image, channel, c_index, eager=False):
    """
    Loads a channel from OMERO image into the napari viewer

    :param  viewer:     napari viewer instance
    :param  image:      omero.gateway.ImageWrapper
    """
    session_id = image._conn._getSessionId()
    if eager:
        data = get_data(image, c=c_index)
    else:
        data = get_data_lazy(image, c=c_index)
    # use current rendering settings from OMERO
    color = channel.getColor().getRGB()
    color = [r / 256 for r in color]
    cmap = Colormap([[0, 0, 0], color])
    win_start = channel.getWindowStart()
    win_end = channel.getWindowEnd()
    win_min = channel.getWindowMin()
    win_max = channel.getWindowMax()
    z_scale = None
    # Z-scale for 3D viewing
    #  NB: This can cause unexpected behaviour
    #  https://forum.image.sc/t/napari-non-integer-step-size/31847
    #  And breaks viewer.dims.set_point(idx, position)
    # if image.getSizeZ() > 1:
    #     size_x = image.getPixelSizeX()
    #     size_z = image.getPixelSizeZ()
    #     if size_x is not None and size_z is not None:
    #         z_scale = [1, size_z / size_x, 1, 1]
    name = channel.getLabel()
    layer = viewer.add_image(
        data,
        blending="additive",
        colormap=("from_omero", cmap),
        scale=z_scale,
        # for saving data/ROIs back to OMERO
        metadata={"image_id": image.id, "session_id": session_id},
        name=name,
    )
    layer._contrast_limits_range = [win_min, win_max]
    layer.contrast_limits = [win_start, win_end]
    return layer


def get_data(img, c=0):
    """
    Get n-dimensional numpy array of pixel data for the OMERO image.

    :param  img:        omero.gateway.ImageWrapper
    :c      int:        Channel index
    """
    sz = img.getSizeZ()
    st = img.getSizeT()
    # get all planes we need
    zct_list = [(z, c, t) for t in range(st) for z in range(sz)]
    pixels = img.getPrimaryPixels()
    planes = []
    for p in pixels.getPlanes(zct_list):
        # self.ctx.out(".", newline=False)
        planes.append(p)
    # self.ctx.out("")
    if sz == 1 or st == 1:
        return numpy.array(planes)
    # arrange plane list into 2D numpy array of planes
    z_stacks = []
    for t in range(st):
        z_stacks.append(numpy.array(planes[t * sz : (t + 1) * sz]))
    return numpy.array(z_stacks)


plane_cache = {}


def get_data_lazy(img, c=0):
    """
    Get n-dimensional dask array, with delayed reading from OMERO image.

    :param  img:        omero.gateway.ImageWrapper
    :c      int:        Channel index
    """
    sz = img.getSizeZ()
    st = img.getSizeT()
    plane_names = ["%s,%s,%s" % (z, c, t) for t in range(st) for z in range(sz)]

    def get_plane(plane_name):
        if plane_name in plane_cache:
            return plane_cache[plane_name]
        z, c, t = [int(n) for n in plane_name.split(",")]
        print("get_plane", z, c, t)
        pixels = img.getPrimaryPixels()
        p = pixels.getPlane(z, c, t)
        plane_cache[plane_name] = p
        return p

    # read the first file to get the shape and dtype
    # ASSUMES THAT ALL FILES SHARE THE SAME SHAPE/TYPE
    sample = get_plane(plane_names[0])

    lazy_imread = delayed(get_plane)  # lazy reader
    lazy_arrays = [lazy_imread(pn) for pn in plane_names]
    dask_arrays = [
        da.from_delayed(delayed_reader, shape=sample.shape, dtype=sample.dtype)
        for delayed_reader in lazy_arrays
    ]
    # Stack into one large dask.array
    if sz == 1 or st == 1:
        return da.stack(dask_arrays, axis=0)

    z_stacks = []
    for t in range(st):
        z_stacks.append(da.stack(dask_arrays[t * sz : (t + 1) * sz], axis=0))
    stack = da.stack(z_stacks, axis=0)
    return stack


def set_dims_labels(viewer, image):
    """
    Set labels on napari viewer dims, based on
    dimensions of OMERO image

    :param  viewer:     napari viewer instance
    :param  image:      omero.gateway.ImageWrapper
    """
    # dims (t, z, y, x) for 5D image
    dims = []
    if image.getSizeT() > 1:
        dims.append("T")
    if image.getSizeZ() > 1:
        dims.append("Z")

    for idx, label in enumerate(dims):
        viewer.dims.set_axis_label(idx, label)


def set_dims_defaults(viewer, image):
    """
    Set Z/T slider index on napari viewer, according
    to default Z/T indecies of the OMERO image

    :param  viewer:     napari viewer instance
    :param  image:      omero.gateway.ImageWrapper
    """
    # dims (t, z, y, x) for 5D image
    dims = []
    if image.getSizeT() > 1:
        dims.append(image.getDefaultT())
    if image.getSizeZ() > 1:
        dims.append(image.getDefaultZ())

    for idx, position in enumerate(dims):
        viewer.dims.set_point(idx, position)


def save_rois(viewer):
    # Usage: In napari, open console and
    # >>> from omero_napari import *
    # >>> save_rois(viewer)

    session_id = get_session_id(viewer)
    conn = BlitzGateway(port=4064, host="localhost")
    print("session_id: %s" % session_id)
    conn.connect(sUuid=session_id)

    image_id = get_image_id(viewer)

    for layer in viewer.layers:
        if layer.name.startswith("Points"):
            for p in layer.data:
                z = p[0]
                y = p[1]
                x = p[2]

                point = PointI()
                point.x = rdouble(x)
                point.y = rdouble(y)
                point.theZ = rint(z)
                point.theT = rint(0)
                roi = create_roi(conn, image_id, [point])
                print("Created ROI: %s" % roi.id.val)

    conn.close()


def get_layers_metadata(viewer, key):
    for layer in viewer.layers:
        if key in layer.metadata:
            return layer.metadata[key]


def get_image_id(viewer):
    return get_layers_metadata(viewer, "image_id")


def get_session_id(viewer):
    return get_layers_metadata(viewer, "session_id")


def create_roi(conn, img_id, shapes):
    updateService = conn.getUpdateService()
    roi = RoiI()
    roi.setImage(ImageI(img_id, False))
    for shape in shapes:
        roi.addShape(shape)
    return updateService.saveAndReturnObject(roi)


# Register omero_napari as an OMERO CLI plugin
if __name__ == "__main__":
    cli = CLI()
    cli.register("napari", NapariControl, HELP)
    cli.invoke(sys.argv[1:])
