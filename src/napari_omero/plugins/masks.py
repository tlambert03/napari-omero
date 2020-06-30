from typing import List
import numpy as np
from random import randint

from omero.gateway import ImageWrapper
from omero.model import RoiI
from omero_rois import mask_from_binary_image


def create_roi(image: ImageWrapper, shapes) -> RoiI:
    updateService = image._conn.getUpdateService()
    roi = RoiI()
    # use the omero.model.ImageI that underlies the 'image' wrapper
    roi.setImage(image._obj)
    for shape in shapes:
        roi.addShape(shape)
    # Save the ROI (saves any linked shapes too)
    return updateService.saveAndReturnObject(roi)


def save_labels(masks_4d: np.ndarray, image: ImageWrapper) -> List[RoiI]:
    """
    Saves masks from a 5D image (no C dimension)

    Each non-zero value in the labels data
    is used to create an ROI in OMERO with a
    Shape Mask created for each Z/T plane of
    the the mask.
    """
    # for each label value, check if we have any masks
    rois = []
    for v in range(1, masks_4d.max() + 1):
        hits = masks_4d.flatten() == v
        if np.any(hits):
            rois.append(save_label(masks_4d == v, image))
    return rois


def save_label(bool_4d: np.ndarray, image: ImageWrapper) -> RoiI:
    """Turns a boolean array of shape (t, z, y, x) into OMERO Roi"""
    size_t = bool_4d.shape[0]
    size_z = bool_4d.shape[1]
    # Create an ROI with a shape for each Z/T that has some mask
    mask_shapes = []
    for z in range(0, size_z):
        for t in range(0, size_t):
            masks_2d = bool_4d[t][z]
            if np.any(masks_2d.flatten()):
                rgba = [randint(0, 255), randint(0, 255), randint(0, 255), 255]
                mask = mask_from_binary_image(masks_2d, rgba=rgba, z=z, t=t)
                mask_shapes.append(mask)

    print(f'Creating ROI with {len(mask_shapes)} shapes')
    return create_roi(image, mask_shapes)
