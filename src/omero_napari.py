
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
            print('clean conn...')
            # if self.gateway is not None:
            #     self.gateway.close(hard=False)
            #     self.gateway = None
            #     self.client = None
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
        self.ctx.out("View image....")

        if isinstance(args.object, ImageI):
            img = self._lookup(self.gateway, "Image", args.object.id)
            print(img.name)

            # session_id = self.gateway._sessionUuid

            with napari.gui_qt():
                viewer = napari.Viewer()
                load_omero_image(viewer, args.object.id, self.gateway)

                print('view close...')
                self.gateway.close(hard=False)
                self.gateway = None


    def _lookup(self, gateway, type, oid):
        # TODO: move _lookup to a _configure type
        gateway.SERVICE_OPTS.setOmeroGroup('-1')
        obj = gateway.getObject(type, oid)
        if not obj:
            self.ctx.die(110, "No such %s: %s" % (type, oid))
        return obj


def get_z_stack(img, c=0, t=0):
    zct_list = [(z, c, t) for z in range(img.getSizeZ())]
    pixels = img.getPrimaryPixels()
    return numpy.array(list(pixels.getPlanes(zct_list)))


def get_t_z_stack(img, c=0):
    sz = img.getSizeZ()
    st = img.getSizeT()
    zct_list = [(z, c, t) for z in range(sz) for t in range(st)]
    pixels = img.getPrimaryPixels()
    planes = list(pixels.getPlanes(zct_list))
    z_stacks = []
    for t in range(st):
        print('T: %s' % t)
        print(len(planes[t * sz: (t + 1) * sz]))
        z_stacks.append(numpy.array(planes[t * sz: (t + 1) * sz]))
    return numpy.array(z_stacks)


def load_omero_image(viewer, image_id, conn):
    """
    Entry point - can be called to initially load an image
    from OMERO, passing in session_id
    OR, with session_id None, 
    lookup session_id from layers already in napari viewer
    """
    # if session_id is None:
    #     # lookup session_id from layers already in napari viewer
    #     session_id = get_session_id(viewer)

    # conn = BlitzGateway(port=4064, host="localhost")
    # conn.connect(sUuid=session_id)

    image = conn.getObject("Image", image_id)
    layers = []
    for c, channel in enumerate(image.getChannels()):
        print('loading channel %s' % c)
        l = load_omero_channel(viewer, image, channel, c)
        layers.append(l)
    return l


def load_omero_channel(viewer, image, channel, c_index):
    session_id = image._conn._sessionUuid
    data = get_t_z_stack(image, c=c_index)
    # use current rendering settings from OMERO
    color = channel.getColor().getRGB()
    color = [r/256 for r in color]
    cmap = Colormap([[0, 0, 0], color])
    z_scale = None
    # Z-scale for 3D viewing
    if image.getSizeZ() > 1:
        size_x = image.getPixelSizeX()
        size_z = image.getPixelSizeZ()
        z_scale = [1, size_z / size_x, 1, 1]
    name=channel.getLabel()
    return viewer.add_image(data, blending='additive',
                        colormap=('from_omero', cmap),
                        scale=z_scale,
                        metadata={'image_id': image.id,
                                'session_id': session_id},
                        name=name)

try:
    register("napari", NapariControl, HELP)
except:
    if __name__ == "__main__":
        cli = CLI()
        cli.register("napari", NapariControl, HELP)
        cli.invoke(sys.argv[1:])
