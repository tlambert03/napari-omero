import sys
import time
from functools import wraps

import numpy
from qtpy.QtWidgets import QPushButton

import napari
import omero.clients  # noqa
from napari.layers.labels.labels import Labels as labels_layer
from napari.layers.points.points import Points as points_layer
from napari.layers.shapes.shapes import Shapes as shapes_layer
from omero.cli import CLI, BaseControl, ProxyStringType
from omero.gateway import BlitzGateway, PixelsWrapper
from omero.model import (
    EllipseI,
    ImageI,
    LineI,
    PointI,
    PolygonI,
    PolylineI,
    RectangleI,
    RoiI,
)
from omero.rtypes import rdouble, rint, rstring

from .masks import save_labels
from ..utils import lookup_obj, obj_to_proxy_string

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
        print(self.gateway)
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
            try:
                img = lookup_obj(self.gateway, args.object)
            except NameError:
                self.ctx.die(110, "No such %s: %s" % (type, args.object.id))

            self.ctx.out("View image: %s" % img.name)

            with napari.gui_qt():
                viewer = napari.Viewer()

                add_buttons(viewer, img)

                n = time.time()
                viewer.open(obj_to_proxy_string(args.object), plugin="omero")
                set_dims_defaults(viewer, img)
                set_dims_labels(viewer, img)
                print(f"time to load_omero_image(): {time.time() - n:.4f} s")

                # add 'conn' and 'omero_image' to the viewer console
                viewer.update_console(
                    {"conn": self.gateway, "omero_image": img}
                )


# Register napari_omero as an OMERO CLI plugin
if __name__ == "__main__":
    cli = CLI()
    cli.register("napari", NapariControl, HELP)
    cli.invoke(sys.argv[1:])


def add_buttons(viewer, img):
    """
    Add custom buttons to the viewer UI
    """

    def handle_save_rois():
        save_rois(viewer, img)

    button = QPushButton("Save ROIs to OMERO")
    button.clicked.connect(handle_save_rois)
    viewer.window.add_dock_widget(button, name="Save OMERO", area="left")


def get_data(img, c=0):
    """
    Get 4D numpy array of pixel data, shape = (size_t, size_z, size_y, size_x)

    :param  img:        omero.gateway.ImageWrapper
    :c      int:        Channel index
    """
    size_z = img.getSizeZ()
    size_t = img.getSizeT()
    # get all planes we need in a single generator
    zct_list = [(z, c, t) for t in range(size_t) for z in range(size_z)]
    pixels = img.getPrimaryPixels()
    plane_gen = pixels.getPlanes(zct_list)

    t_stacks = []
    for t in range(size_t):
        z_stack = []
        for z in range(size_z):
            print("plane c:%s, t:%s, z:%s" % (c, t, z))
            z_stack.append(next(plane_gen))
        t_stacks.append(numpy.array(z_stack))
    return numpy.array(t_stacks)


def set_dims_labels(viewer, image):
    """
    Set labels on napari viewer dims, based on
    dimensions of OMERO image

    :param  viewer:     napari viewer instance
    :param  image:      omero.gateway.ImageWrapper
    """
    # dims (t, z, y, x) for 5D image
    dims = "TZ"

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
    if image.getSizeT() > 1:
        viewer.dims.set_point(0, image.getDefaultT())
    if image.getSizeZ() > 1:
        viewer.dims.set_point(1, image.getDefaultZ())


def save_rois(viewer, image):
    """
    Usage: In napari, open console...
    >>> from napari_omero import *
    >>> save_rois(viewer, omero_image)
    """
    conn = image._conn

    for layer in viewer.layers:
        if type(layer) == points_layer:
            for p in layer.data:
                point = create_omero_point(p)
                roi = create_roi(conn, image.id, [point])
                print("Created ROI: %s" % roi.id.val)
        elif type(layer) == shapes_layer:
            if len(layer.data) == 0 or len(layer.shape_type) == 0:
                continue
            shape_types = layer.shape_type
            if isinstance(shape_types, str):
                shape_types = [
                    layer.shape_type for t in range(len(layer.data))
                ]
            for shape_type, data in zip(shape_types, layer.data):
                shape = create_omero_shape(shape_type, data)
                if shape is not None:
                    roi = create_roi(conn, image.id, [shape])
                    print("Created ROI: %s" % roi.id.val)
        elif type(layer) == labels_layer:
            print("Saving Labels...")
            save_labels(layer, image)


def get_x(coordinate):
    return coordinate[-1]


def get_y(coordinate):
    return coordinate[-2]


def get_t(coordinate):
    return coordinate[0]


def get_z(coordinate):
    return coordinate[1]


def create_omero_point(data):
    point = PointI()
    point.x = rdouble(get_x(data))
    point.y = rdouble(get_y(data))
    point.theZ = rint(get_z(data))
    point.theT = rint(get_t(data))
    return point


def create_omero_shape(shape_type, data):
    # "line", "path", "polygon", "rectangle", "ellipse"
    # NB: assume all points on same plane.
    # Use first point to get Z and T index
    z_index = get_z(data[0])
    t_index = get_t(data[0])
    shape = None
    if shape_type == "line":
        shape = LineI()
        shape.x1 = rdouble(get_x(data[0]))
        shape.y1 = rdouble(get_y(data[0]))
        shape.x2 = rdouble(get_x(data[1]))
        shape.y2 = rdouble(get_y(data[1]))
    elif shape_type == "path" or shape_type == "polygon":
        shape = PolylineI() if shape_type == "path" else PolygonI()
        # points = "10,20, 50,150, 200,200, 250,75"
        points = [f"{get_x(d)},{get_y(d)}" for d in data]
        shape.points = rstring(", ".join(points))
    elif shape_type == "rectangle" or shape_type == "ellipse":
        # corners go anti-clockwise starting top-left
        x1 = get_x(data[0])
        x2 = get_x(data[1])
        x3 = get_x(data[2])
        x4 = get_x(data[3])
        y1 = get_y(data[0])
        y2 = get_y(data[1])
        y3 = get_y(data[2])
        y4 = get_y(data[3])
        if shape_type == "rectangle":
            # Rectangle not rotated
            if x1 == x2:
                shape = RectangleI()
                # TODO: handle 'updside down' rectangle x3 < x1
                shape.x = rdouble(x1)
                shape.y = rdouble(y1)
                shape.width = rdouble(x3 - x1)
                shape.height = rdouble(y2 - y1)
            else:
                # Rotated Rectangle - save as Polygon
                shape = PolygonI()
                points = f"{x1},{y1}, {x2},{y2}, {x3},{y3}, {x4},{y4}"
                shape.points = rstring(points)
        elif shape_type == "ellipse":
            # Ellipse not rotated (ignore floating point rouding)
            if int(x1) == int(x2):
                shape = EllipseI()
                shape.x = rdouble((x1 + x3) / 2)
                shape.y = rdouble((y1 + y2) / 2)
                shape.radiusX = rdouble(abs(x3 - x1) / 2)
                shape.radiusY = rdouble(abs(y2 - y1) / 2)
            else:
                # TODO: Need to calculate transformation matrix
                print("Rotated Ellipse not yet supported!")

    if shape is not None:
        shape.theZ = rint(z_index)
        shape.theT = rint(t_index)
    return shape


def create_roi(conn, img_id, shapes):
    updateService = conn.getUpdateService()
    roi = RoiI()
    roi.setImage(ImageI(img_id, False))
    for shape in shapes:
        roi.addShape(shape)
    return updateService.saveAndReturnObject(roi)


class NonCachedPixelsWrapper(PixelsWrapper):
    """Extend gateway.PixelWrapper to override _prepareRawPixelsStore."""

    def _prepareRawPixelsStore(self):
        """
        Creates RawPixelsStore and sets the id etc

        This overrides the superclass behaviour to make sure that
        we don't re-use RawPixelStore in multiple processes since
        the Store may be closed in 1 process while still needed elsewhere.
        This is needed when napari requests may planes simultaneously,
        e.g. when switching to 3D view.
        """
        ps = self._conn.c.sf.createRawPixelsStore()
        ps.setPixelsId(self._obj.id.val, True, self._conn.SERVICE_OPTS)
        return ps


omero.gateway.PixelsWrapper = NonCachedPixelsWrapper
# Update the BlitzGateway to use our NonCachedPixelsWrapper
omero.gateway.refreshWrappers()
