
from functools import wraps

import omero.clients
from omero.rtypes import rdouble, rint
from omero.model import PointI, ImageI, RoiI
from omero.gateway import BlitzGateway

try:
    from vispy.color import Colormap
except ImportError:
    pass

try:
    import napari
except ImportError:
    pass

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

        napari_type = ProxyStringType("Image")

        for x in (view,):
            x.add_argument("object", type=napari_type,
                           help="Object to view")


    @gateway_required
    def view(self, args):

        if isinstance(args.object, ImageI):
            img = self._lookup(self.gateway, "Image", args.object.id)
            self.ctx.out("View image: %s" % img.name)

            with napari.gui_qt():
                viewer = napari.Viewer()
                load_omero_image(viewer, img)


    def _lookup(self, gateway, type, oid):
        """Find object of type by ID."""
        gateway.SERVICE_OPTS.setOmeroGroup('-1')
        obj = gateway.getObject(type, oid)
        if not obj:
            self.ctx.die(110, "No such %s: %s" % (type, oid))
        return obj


def load_omero_image(viewer, image):
    """
    Entry point - can be called to initially load an image
    from OMERO into the napari viewer

    :param  viewer:     napari viewer instance
    :param  image:      omero.gateway.ImageWrapper
    """
    layers = []
    for c, channel in enumerate(image.getChannels()):
        # self.ctx.out('loading channel %s:' % c, newline=False)
        l = load_omero_channel(viewer, image, channel, c)
        layers.append(l)

    set_dims_defaults(viewer, image)
    set_dims_labels(viewer, image)
    return l


def load_omero_channel(viewer, image, channel, c_index):
    """
    Loads a channel from OMERO image into the napari viewer

    :param  viewer:     napari viewer instance
    :param  image:      omero.gateway.ImageWrapper
    """
    session_id = image._conn._getSessionId()
    data = get_t_z_stack(image, c=c_index)
    # use current rendering settings from OMERO
    color = channel.getColor().getRGB()
    color = [r/256 for r in color]
    cmap = Colormap([[0, 0, 0], color])
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
    name=channel.getLabel()
    return viewer.add_image(data, blending='additive',
                        colormap=('from_omero', cmap),
                        scale=z_scale,
                        # for saving data/ROIs back to OMERO
                        metadata={'image_id': image.id,
                                    'session_id': session_id},
                        name=name)


def get_t_z_stack(img, c=0):
    """
    Entry point - can be called to initially load an image
    from OMERO into the napari viewer

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
        z_stacks.append(numpy.array(planes[t * sz: (t + 1) * sz]))
    return numpy.array(z_stacks)


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
    print('session_id: %s' % session_id)
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
    return get_layers_metadata(viewer, 'image_id')


def get_session_id(viewer):
    return get_layers_metadata(viewer, 'session_id')


def create_roi(conn, img_id, shapes):
    updateService = conn.getUpdateService()
    roi = RoiI()
    roi.setImage(ImageI(img_id, False))
    for shape in shapes:
        roi.addShape(shape)
    return updateService.saveAndReturnObject(roi)


try:
    register("napari", NapariControl, HELP)
except:
    if __name__ == "__main__":
        cli = CLI()
        cli.register("napari", NapariControl, HELP)
        cli.invoke(sys.argv[1:])
