import numpy as np
import math
import struct
import zarr
from random import randint

from omero.model import MaskI, RoiI
from omero.rtypes import rint, rdouble
from omero.gateway import BlitzGateway


def numpy_to_bytearray(numpy_mask):

    # Set correct number of bytes per value
    mask_array = numpy_mask.astype(np.uint8)
    # Convert the mask to bytes
    mask_bytes = mask_array.tostring()
    # Pack the bytes to a bit mask
    divider = 8
    format_string = "B"  # Unsigned char
    byte_factor = 1
    steps = math.ceil(len(mask_bytes) / divider)
    mask = []
    for i in range(int(steps)):
        binary = mask_bytes[i * divider : (i + 1) * divider]
        format = f'{int(byte_factor * len(binary))}{ format_string }'
        binary = struct.unpack(format, binary)
        s = ""
        for bit in binary:
            s += str(bit)
        mask.append(int(s, 2))
    return bytearray(mask)


def crop_plane_to_mask(bool_plane):

    plane_h, plane_w = bool_plane.shape
    # list of booleans
    cols = np.any(bool_plane, axis=0)
    rows = np.any(bool_plane, axis=1)

    # find bounding box
    x = np.argmax(cols)  # 0
    y = np.argmax(rows)  # 1
    cols_reverse = cols[::-1]  # copy with 'step' -1
    rows_reverse = rows[::-1]
    x2 = plane_w - np.argmax(cols_reverse)
    y2 = plane_h - np.argmax(rows_reverse)
    mask_w = x2 - x
    mask_h = y2 - y

    cropped = bool_plane[y:y2, x:x2]
    return (x, y, mask_w, mask_h, cropped)


def create_roi(image, shapes):
    updateService = image._conn.getUpdateService()
    roi = RoiI()
    # use the omero.model.ImageI that underlies the 'image' wrapper
    roi.setImage(image._obj)
    for shape in shapes:
        roi.addShape(shape)
    # Save the ROI (saves any linked shapes too)
    return updateService.saveAndReturnObject(roi)


def save_labels(masks_4d, image):
    """
    Saves masks from a 5D image (no C dimension)

    Each non-zero value in the labels data
    is used to create an ROI in OMERO with a
    Shape Mask created for each Z/T plane of
    the the mask.
    """
    print('masks_4d.shape', masks_4d.shape)
    print('min, max', masks_4d.min(), masks_4d.max())

    # for each label value, check if we have any masks
    for v in range(1, masks_4d.max() + 1):
        hits = masks_4d.flatten() == v
        if np.any(hits):
            save_label(masks_4d == v, image)


def save_label(bool_4d, image):

    size_t = bool_4d.shape[0]
    size_z = bool_4d.shape[1]
    # Create an ROI with a shape for each Z/T that has some mask
    mask_shapes = []
    for z in range(0, size_z):
        for t in range(0, size_t):
            masks_2d = bool_4d[t][z]
            if np.any(masks_2d.flatten()):
                print('create mask shape, z:', z)
                x, y, w, h, cropped = crop_plane_to_mask(masks_2d)
                packed_bypes = numpy_to_bytearray(cropped)
                mask = MaskI()
                mask.setTheZ(rint(z))
                mask.setTheT(rint(t))
                mask.setX(rdouble(x))
                mask.setY(rdouble(y))
                mask.setWidth(rdouble(w))
                mask.setHeight(rdouble(h))
                rgba = [randint(0, 255), randint(0, 255), randint(0, 255), 255]
                color = int.from_bytes(rgba, byteorder='big', signed=True)
                mask.setFillColor(rint(color))
                mask.setBytes(packed_bypes)
                mask_shapes.append(mask)

    print(f'Creating ROI with {len(mask_shapes)} shapes')
    create_roi(image, mask_shapes)
