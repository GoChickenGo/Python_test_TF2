# -*- coding: utf-8 -*-
"""
Created on Sat Mar  7 16:46:47 2020

@author: xinmeng
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import math
import time
from skimage import img_as_ubyte
from skimage.filters import threshold_otsu, threshold_local
from skimage.filters.rank import entropy
from skimage.segmentation import clear_border
from skimage.measure import label, perimeter, find_contours
from skimage.morphology import (
    closing,
    square,
    opening,
    reconstruction,
    skeletonize,
    convex_hull_image,
    dilation,
    thin,
    binary_erosion,
    disk,
    binary_dilation,
)
from skimage.measure import regionprops, moments, moments_central, moments_hu
from skimage.draw import line, polygon2mask, polygon_perimeter
from skimage.color import label2rgb, gray2rgb, rgb2gray
from skimage.restoration import denoise_tv_chambolle
from skimage.io import imread
from skimage.transform import rotate, resize
from scipy.signal import convolve2d
import skimage.external.tifffile as skimtiff
from PIL import Image
from PIL.TiffTags import TAGS
import scipy.interpolate as interpolate
from scipy.ndimage.filters import gaussian_filter1d
from scipy import fftpack
from scipy.optimize import curve_fit
import scipy
import pylab
import os
import pandas as pd
import cv2

# import plotly.express as px

# ================================================================ProcessImage============================================================
class ProcessImage:
    #%%
    """
    # =========================================================================
    #       Retrive scanning scheme and read in images.
    # =========================================================================
    """

    def ReadinImgs_Roundstack(Nest_data_directory, rowIndex, colIndex):
        """
        Read in images from nest directory.

        Parameters
        ----------
        Nest_data_directory : string.
            The directory to folder where the screening data is stored.
        rowIndex, colIndex:
            Row and column index in stage coordinates.

        Returns
        -------
        PMT_image_wholetrace_stack : 2-D ndarray or stack of 2-D ndarray.
            Loaded images.
        """
        fileNameList = []
        ImgSequenceNum = 0
        for file in os.listdir(Nest_data_directory):
            if "PMT_0Zmax" in file and "R{}C{}".format(rowIndex, colIndex) in file:
                fileNameList.append(file)

        fileNameList.sort(
            key=lambda x: int(x[x.index("Round") + 5 : x.index("_Coord")])
        )  # Sort the list according to Round number
        #        print(fileNameList)

        for eachfile in fileNameList:
            ImgSequenceNum += 1
            img_fileName = os.path.join(Nest_data_directory, eachfile)
            temp_loaded_image = imread(img_fileName, as_gray=True)
            temp_loaded_image = temp_loaded_image[np.newaxis, :, :]
            if ImgSequenceNum == 1:
                PMT_image_wholetrace_stack = temp_loaded_image
            else:
                PMT_image_wholetrace_stack = np.concatenate(
                    (PMT_image_wholetrace_stack, temp_loaded_image), axis=0
                )

        return PMT_image_wholetrace_stack

    def retrive_scanning_scheme(
        Nest_data_directory, row_data_folder=True, file_keyword="PMT_0Zmax"
    ):
        """
        # =============================================================================
        # Return lists that contain round sequence and coordinates strings, like ['Coords1_R0C0', 'Coords2_R0C1500']
        # =============================================================================
        Parameters
        ----------
        Nest_data_directory : string.
            The directory to folder where the screening data is stored.
        row_data_folder: bool.
            If selectively add the file names.

        Returns
        -------
        RoundNumberList : List.
            List of all round numbers in screening.
        CoordinatesList : List.
            List of all stage coordinates in screening scheme.
        fileNameList: List.
            List of file names strings.
        """
        fileNameList = []

        for file in os.listdir(Nest_data_directory):
            if row_data_folder == True:
                if file_keyword in file:
                    fileNameList.append(file)
            elif "Thumbs" not in file:
                fileNameList.append(file)

        RoundNumberList = []
        CoordinatesList = []
        for eachfilename in fileNameList:

            # Get how many rounds are there
            try:
                RoundNumberList.append(
                    eachfilename[
                        eachfilename.index("Round") : eachfilename.index("_Grid")
                    ]
                )
            except:
                RoundNumberList.append(
                    eachfilename[
                        eachfilename.index("Round") : eachfilename.index("_Coord")
                    ]
                )

            RoundNumberList = list(dict.fromkeys(RoundNumberList))  # Remove Duplicates

            if row_data_folder == True:
                # Get the coordinates, R_C_
                if "_PMT" in eachfilename:
                    CoordinatesList.append(
                        eachfilename[
                            eachfilename.index("_R") + 1 : eachfilename.index("_PMT")
                        ]
                    )
                    CoordinatesList = list(dict.fromkeys(CoordinatesList))
                elif "Cam" in eachfilename:
                    CoordinatesList.append(
                        eachfilename[
                            eachfilename.index("_R") + 1 : eachfilename.index("_Cam")
                        ]
                    )
                    CoordinatesList = list(dict.fromkeys(CoordinatesList))
            else:
                # Get the coordinates, R_C_
                CoordinatesList.append(
                    eachfilename[eachfilename.index("_R") + 1 : len(eachfilename)]
                )
                CoordinatesList = list(dict.fromkeys(CoordinatesList))

        #        print(CoordinatesList)
        return RoundNumberList, CoordinatesList, fileNameList

    #%%
    """           
    # =========================================================================
    #       Individual image processing    
    # =========================================================================
    """

    def generate_mask(
        imagestack, openingfactor=2, closingfactor=3, binary_adaptive_block_size=335
    ):
        """
        Return a rough binary mask generated from single image or first image of the stack using adaptive thresholding.

        Parameters
        ----------
        imagestack : stack of 2-D ndarray.
            The directory to folder where the screening data is stored.
        openingfactor:
            Degree of morphology opening operation on adaptive thresholded input image.
        closingfactor:
            Degree of morphology closing operation on adaptive thresholded input image.
        binary_adaptive_block_size:
            Block size applied for adaptive thresholding.

        Returns
        -------
        RegionProposal_Mask : 2-D ndarray.
            Binary mask for cells.
        RegionProposal_ImgInMask : 2-D ndarray.
            Denoised image with cell binary mask imposed.
        """
        if imagestack.ndim == 3:
            template_image = imagestack[
                0, :, :
            ]  # Get the first image of the stack to generate the mask for Region Proposal
        elif imagestack.ndim == 2:
            template_image = imagestack

        template_image = denoise_tv_chambolle(
            template_image, weight=0.01
        )  # Denoise the image.
        # -----------------------------------------------Adaptive thresholding-----------------------------------------------
        #        block_size = binary_adaptive_block_size#335
        AdaptiveThresholding = threshold_local(
            template_image, binary_adaptive_block_size, offset=0
        )
        BinaryMask = template_image >= AdaptiveThresholding
        OpeningBinaryMask = opening(BinaryMask, square(int(openingfactor)))
        RegionProposal_Mask = closing(OpeningBinaryMask, square(int(closingfactor)))

        RegionProposal_ImgInMask = RegionProposal_Mask * template_image

        return RegionProposal_Mask, RegionProposal_ImgInMask

    def Region_Proposal(
        image,
        RegionProposalMask,
        smallest_size,
        biggest_size,
        lowest_region_intensity,
        Roundness_thres,
        DeadPixelPercentageThreshold,
        contour_thres,
        contour_dilationparameter,
        cell_region_opening_factor,
        cell_region_closing_factor,
    ):
        """
        Based on tag fluorescence image, generate region proposal bounding box.

        Parameters
        ----------
        image : ndarray
            Input image.
        RegionProposalMask : ndarray
            The binary mask for region iterative analysis.
        smallest_size : int
            Cells size out of this range are ignored.
        biggest_size : int
            Cells size out of this range are ignored.
        lowest_region_intensity : float
            Cells with mean region intensity below this are ignored.
        Roundness_thres : float
            Roundness above this are ignored.
        DeadPixelPercentageThreshold : float
            Percentage of saturated pixels.
        contour_thres : float
            Threshold for contour recognizition.
        contour_dilationparameter : int
            The dilation degree applied when doing inward contour dilation for thicker menbrane area.
        cell_region_opening_factor : TYPE
            Degree of opening operation on individual cell mask.
        cell_region_closing_factor : TYPE
            Degree of closing operation on individual cell mask..

        Returns
        -------
        TagFluorescenceLookupBook : structured array.

        """

        cleared = RegionProposalMask.copy()
        clear_border(cleared)
        # label image regions, prepare for regionprops
        label_image = label(cleared)
        dtype = [
            ("BoundingBox", "U32"),
            ("Mean intensity", float),
            ("Mean intensity in contour", float),
            ("Contour soma ratio", float),
            ("Roundness", float),
        ]
        CellSequenceInRegion = 0
        dirforcellprp = {}
        show_img = False
        if show_img == True:
            plt.figure()
            fig_showlabel, ax_showlabel = plt.subplots(ncols=1, nrows=1, figsize=(6, 6))
            ax_showlabel.imshow(image)  # Show the first image
        for region in regionprops(label_image, intensity_image=image):

            # skip small images
            if (
                region.area > smallest_size
                and region.mean_intensity > lowest_region_intensity
                and region.area < biggest_size
            ):

                # draw rectangle around segmented coins
                minr, minc, maxr, maxc = region.bbox
                boundingbox_info = "minr{}_minc{}_maxr{}_maxc{}".format(
                    minr, minc, maxr, maxc
                )
                bbox_area = (maxr - minr) * (maxc - minc)
                # Based on the boundingbox for each cell from first image in the stack, raw image of slightly larger region is extracted from each round.
                RawRegionImg = image[
                    max(minr - 4, 0) : min(maxr + 4, image[0].shape[0]),
                    max(minc - 4, 0) : min(maxc + 4, image[0].shape[0]),
                ]  # Raw region image

                RawRegionImg_for_contour = RawRegionImg.copy()

                # ---------Get the cell filled mask-------------
                (
                    filled_mask_bef,
                    MeanIntensity_Background,
                ) = ProcessImage.get_cell_filled_mask(
                    RawRegionImg=RawRegionImg,
                    region_area=bbox_area * 0.2,
                    cell_region_opening_factor=cell_region_opening_factor,
                    cell_region_closing_factor=cell_region_closing_factor,
                )

                filled_mask_convolve2d = ProcessImage.smoothing_filled_mask(
                    RawRegionImg,
                    filled_mask_bef=filled_mask_bef,
                    region_area=bbox_area * 0.2,
                    threshold_factor=1.1,
                )

                # Find contour along filled image
                contour_mask_thin_line = ProcessImage.contour(
                    filled_mask_convolve2d,
                    RawRegionImg_for_contour.copy(),
                    contour_thres,
                )

                # after here intensityimage_intensity is changed from contour labeled with number 5 to binary image
                contour_mask_of_cell = ProcessImage.inward_mask_dilation(
                    contour_mask_thin_line.copy(),
                    filled_mask_convolve2d,
                    contour_dilationparameter,
                )

                #                    Calculate Roundness
                # --------------------------------------------------------------
                filled_mask_area = len(np.where(filled_mask_convolve2d == 1)[0])
                contour_mask_perimeter = len(np.where(contour_mask_thin_line == 1)[0])
                Roundness = 4 * 3.1415 * filled_mask_area / contour_mask_perimeter ** 2
                #                print('Roundness: {}'.format(4*3.1415*filled_mask_area/contour_mask_perimeter**2))

                #                    Calculate central moments
                # --------------------------------------------------------------
                #                M = moments(filled_mask_convolve2d)
                #                centroid = (M[1, 0] / M[0, 0], M[0, 1] / M[0, 0])
                #                Img_moments_central = moments_central(filled_mask_convolve2d, centroid, order=4)
                ##                print(Img_moments_central)
                #                Img_moments_hu = moments_hu(Img_moments_central/np.amax(Img_moments_central))
                #
                #                # Log scale hu moments
                #                for EachMoment in range(len(Img_moments_hu)):
                #                    Img_moments_hu[EachMoment] = -1* np.copysign(1.0, Img_moments_hu[EachMoment]) * np.log10(abs(Img_moments_hu[EachMoment]))

                #                print(sum(Img_moments_hu[0:4]))
                #                print('Img_moments_hu is {}'.format(Img_moments_hu))

                # --------------------------------------------------------------
                # Roundness Threshold
                if Roundness < Roundness_thres:
                    MeanIntensity_FilledArea = (
                        np.mean(RawRegionImg[np.where(filled_mask_bef == 1)])
                        - MeanIntensity_Background
                    )  # Mean pixel value of filled raw cell area

                    MeanIntensity_Contour = (
                        np.mean(RawRegionImg[np.where(contour_mask_of_cell == 1)])
                        - MeanIntensity_Background
                    )

                    soma_mask_of_cell = filled_mask_convolve2d - contour_mask_of_cell
                    MeanIntensity_Soma = (
                        np.mean(RawRegionImg[np.where(soma_mask_of_cell == 1)])
                        - MeanIntensity_Background
                    )  # Mean pixel value of soma area
                    contour_soma_ratio = MeanIntensity_Contour / MeanIntensity_Soma

                    Cell_Area_Img = filled_mask_convolve2d * RawRegionImg
                    # Calculate the entrophy of the image.
                    #                entr_img = entropy(Cell_Area_Img/np.amax(Cell_Area_Img), disk(5))
                    #                print(np.mean(entr_img))

                    # ---------------------Calculate dead pixels----------------
                    DeadPixelNum = len(np.where(Cell_Area_Img >= 3.86)[0])
                    filled_mask_convolve2d_area = len(
                        np.where(filled_mask_convolve2d >= 0)[0]
                    )
                    DeadPixelPercentage = round(
                        DeadPixelNum / filled_mask_convolve2d_area, 3
                    )
                    #                    print('Dead Pixel percentage: {}'.format(DeadPixelPercentage)) # b[np.where(aa==16)]=2

                    if str(MeanIntensity_FilledArea) == "nan":
                        MeanIntensity_FilledArea = 0
                    if str(MeanIntensity_Contour) == "nan":
                        MeanIntensity_Contour = 0
                    if str(contour_soma_ratio) == "nan":
                        contour_soma_ratio = 0

                    if DeadPixelPercentage <= DeadPixelPercentageThreshold:

                        dirforcellprp[CellSequenceInRegion] = (
                            boundingbox_info,
                            MeanIntensity_FilledArea,
                            MeanIntensity_Contour,
                            contour_soma_ratio,
                            Roundness,
                        )

                        #                    plt.figure()
                        #                    plt.imshow(RawRegionImg)
                        #                    plt.show()
                        #    # #
                        #                    plt.figure()
                        #                    plt.imshow(filled_mask_convolve2d)
                        #                    plt.show()

                        # --------------------------------------------------Add red boundingbox to axis----------------------------------------------
                        rect = mpatches.Rectangle(
                            (minc, minr),
                            maxc - minc,
                            maxr - minr,
                            fill=False,
                            edgecolor="red",
                            linewidth=2,
                        )
                        contour_mean_bef_rounded = str(round(MeanIntensity_Contour, 3))[
                            0:5
                        ]

                        if show_img == True:
                            ax_showlabel.add_patch(rect)
                            ax_showlabel.text(
                                (maxc + minc) / 2,
                                (maxr + minr) / 2,
                                "Cell-{}, {}: {}".format(
                                    CellSequenceInRegion,
                                    "c_m",
                                    contour_mean_bef_rounded,
                                ),
                                fontsize=8,
                                color="yellow",
                                style="italic",
                            )  # ,bbox={'facecolor':'red', 'alpha':0.3, 'pad':8})

                        CellSequenceInRegion += 1
        if show_img == True:
            ax_showlabel.set_axis_off()
            plt.show()

        TagFluorescenceLookupBook = np.zeros(CellSequenceInRegion, dtype=dtype)
        for p in range(CellSequenceInRegion):
            TagFluorescenceLookupBook[p] = dirforcellprp[p]

        return TagFluorescenceLookupBook

    def extract_information_from_bbox(
        image,
        bbox_list,
        DeadPixelPercentageThreshold,
        contour_thres,
        contour_dilationparameter,
        cell_region_opening_factor,
        cell_region_closing_factor,
    ):
        """
        Extract information from bounding box in image.

        Parameters
        ----------
        image : 2-D ndarray.
            Input image.
        bbox_list: List of strings.
            List of each cell's bounding box.
        DeadPixelPercentageThreshold:
            Threshold of percentage of saturated pixels in input image.
        contour_thres:
            Threshold used when finding cell contour.
        contour_dilationparameter:
            Degree of morphology dilation operation for generating contour mask from contour line.
        cell_region_opening_factor:
             Degree of morphology opening operation when generating the filled mask for cell.
        cell_region_closing_factor:
             Degree of morphology closing operation when generating the filled mask for cell.

        Returns
        -------
        LibFluorescenceLookupBook : Dictionary.
            Dictionary with all cells' information in dtype.

        """

        dtype = [
            ("BoundingBox", "U32"),
            ("Mean intensity", float),
            ("Mean intensity in contour", float),
            ("Contour soma ratio", float),
        ]
        CellSequenceInRegion = 0
        dirforcellprp = {}

        show_img = False
        if show_img == True:
            plt.figure()
            fig_showlabel, ax_showlabel = plt.subplots(ncols=1, nrows=1, figsize=(6, 6))
            ax_showlabel.imshow(image)  # Show the first image

        for Each_bounding_box in bbox_list:

            # Retrieve boundingbox information
            minr = int(
                Each_bounding_box[
                    Each_bounding_box.index("minr")
                    + 4 : Each_bounding_box.index("_minc")
                ]
            )
            maxr = int(
                Each_bounding_box[
                    Each_bounding_box.index("maxr")
                    + 4 : Each_bounding_box.index("_maxc")
                ]
            )
            minc = int(
                Each_bounding_box[
                    Each_bounding_box.index("minc")
                    + 4 : Each_bounding_box.index("_maxr")
                ]
            )
            maxc = int(
                Each_bounding_box[
                    Each_bounding_box.index("maxc") + 4 : len(Each_bounding_box)
                ]
            )

            # Based on the boundingbox for each cell from first image in the stack, raw image of slightly larger region is extracted from each round.
            RawRegionImg = image[
                max(minr - 4, 0) : min(maxr + 4, image[0].shape[0]),
                max(minc - 4, 0) : min(maxc + 4, image[0].shape[0]),
            ]  # Raw region image

            RawRegionImg_for_contour = RawRegionImg.copy()

            # ---------Get the cell filled mask-------------
            bbox_area = (maxr - minr) * (maxc - minc)

            (
                filled_mask_bef,
                MeanIntensity_Background,
            ) = ProcessImage.get_cell_filled_mask(
                RawRegionImg=RawRegionImg,
                region_area=bbox_area * 0.2,
                cell_region_opening_factor=cell_region_opening_factor,
                cell_region_closing_factor=cell_region_closing_factor,
            )

            filled_mask_convolve2d = ProcessImage.smoothing_filled_mask(
                RawRegionImg,
                filled_mask_bef=filled_mask_bef,
                region_area=bbox_area * 0.2,
                threshold_factor=1.1,
            )

            # Find contour along filled image
            contour_mask_thin_line = ProcessImage.findContour(
                filled_mask_convolve2d, RawRegionImg_for_contour.copy(), contour_thres
            )

            # after here intensityimage_intensity is changed from contour labeled with number 5 to binary image
            contour_mask_of_cell = ProcessImage.inward_mask_dilation(
                contour_mask_thin_line.copy(),
                filled_mask_convolve2d,
                contour_dilationparameter,
            )

            # Calculate mean values.
            # --------------------------------------------------------------
            MeanIntensity_FilledArea = (
                np.mean(RawRegionImg[np.where(filled_mask_bef == 1)])
                - MeanIntensity_Background
            )  # Mean pixel value of filled raw cell area

            MeanIntensity_Contour = (
                np.mean(RawRegionImg[np.where(contour_mask_of_cell == 1)])
                - MeanIntensity_Background
            )

            soma_mask_of_cell = filled_mask_convolve2d - contour_mask_of_cell
            MeanIntensity_Soma = (
                np.mean(RawRegionImg[np.where(soma_mask_of_cell == 1)])
                - MeanIntensity_Background
            )  # Mean pixel value of soma area
            contour_soma_ratio = MeanIntensity_Contour / MeanIntensity_Soma

            Cell_Area_Img = filled_mask_convolve2d * RawRegionImg

            # ---------------------Calculate dead pixels----------------
            DeadPixelNum = len(np.where(Cell_Area_Img >= 3.86)[0])
            filled_mask_convolve2d_area = len(np.where(filled_mask_convolve2d >= 0)[0])
            DeadPixelPercentage = round(DeadPixelNum / filled_mask_convolve2d_area, 3)

            if str(MeanIntensity_FilledArea) == "nan":
                MeanIntensity_FilledArea = 0
            if str(MeanIntensity_Contour) == "nan":
                MeanIntensity_Contour = 0
            if str(contour_soma_ratio) == "nan":
                contour_soma_ratio = 0

            if DeadPixelPercentage <= DeadPixelPercentageThreshold:
                dirforcellprp[CellSequenceInRegion] = (
                    Each_bounding_box,
                    MeanIntensity_FilledArea,
                    MeanIntensity_Contour,
                    contour_soma_ratio,
                )

                # plt.figure()
                # plt.imshow(RawRegionImg)
                # plt.show()

                # plt.figure()
                # plt.imshow(contour_mask_of_cell)
                # plt.show()

                # --------------------------------------------------Add red boundingbox to axis----------------------------------------------
                rect = mpatches.Rectangle(
                    (minc, minr),
                    maxc - minc,
                    maxr - minr,
                    fill=False,
                    edgecolor="red",
                    linewidth=2,
                )
                contour_mean_bef_rounded = str(round(MeanIntensity_Contour, 3))[0:5]

                if show_img == True:
                    ax_showlabel.add_patch(rect)
                    ax_showlabel.text(
                        (maxc + minc) / 2,
                        (maxr + minr) / 2,
                        "Cell-{}, {}: {}".format(
                            CellSequenceInRegion, "c_m", contour_mean_bef_rounded
                        ),
                        fontsize=8,
                        color="yellow",
                        style="italic",
                    )

                CellSequenceInRegion += 1

        if show_img == True:
            ax_showlabel.set_axis_off()
            plt.show()

        LibFluorescenceLookupBook = np.zeros(CellSequenceInRegion, dtype=dtype)
        for p in range(CellSequenceInRegion):
            LibFluorescenceLookupBook[p] = dirforcellprp[p]

        return LibFluorescenceLookupBook

    def if_theres_cell(image, percentage_threshold=0.0008):
        """
        Check if there're enough objects in the image.

        Parameters
        ----------
        image : np.array
            Input image.
        percentage_threshold : float, optional
            Threshold for the percentage of pixels identifies as object of interest.
            The default is 0.0085.

        Returns
        -------
        bool
            DESCRIPTION.

        """
        # Get the thresholded mask
        image_binary = np.where(image >= threshold_otsu(image), 1, 0)
        # Opening on the mask to diminish tiny patches from noise
        image_binary_open = opening(image_binary, square(3))
        # Closing on the mask
        image_binary_close = closing(image_binary_open, square(4))
        # Loop through regions to find the biggest area
        area_list = []
        for region in regionprops(label(image_binary_close)):
            area_list.append(region.area)

        try:
            if len(area_list) > 0:
                if max(area_list) / image.size > percentage_threshold:
                    return True
                else:
                    return False
        except:
            return False

    #%%
    """           
    # =========================================================================
    #     Contour scanning processing       
    # =========================================================================
    """

    def findContour(imagewithouthole, image, threshold):
        """
        Return contour mask by eroding inward from filled cell mask.

        Parameters
        ----------
        imagewithouthole : 2-D ndarray.
            Input filled image.
        image : 2-D ndarray.
            Raw image.
        threshold : Float.
            Threshold for finding contour.

        Returns
        -------
        binarycontour : 2-D ndarray.
            Binary contour mask.
        """
        contours = find_contours(
            imagewithouthole, threshold
        )  # Find iso-valued contours in a 2D array for a given level value.

        for n, contour in enumerate(contours):
            # print(contour[1,0])
            col = contour[:, 1]
            row = contour[:, 0]
            col1 = [int(round(i)) for i in col]
            row1 = [int(round(i)) for i in row]

            for m in range(len(col1)):
                image[row1[m], col1[m]] = 5
                # filledimg[contour[:, 0], contour[:, 1]] = 2
            # ax.plot(contour[:, 1]+minc, contour[:, 0]+minr, linewidth=3, color='yellow')
        binarycontour = np.where(image == 5, 1, 0)

        return binarycontour

    def inward_mask_dilation(contour_skeleton, mask_without_holes, dilation_parameter):
        """
        Perform inward dilation on contour skeleton

        Parameters
        ----------
        contour_skeleton : ndarray
            Binary skeleton of contour.
        mask_without_holes : ndarray
            Filled whole cell mask.
        dilation_parameter : float
            Degree of dilation.

        Returns
        -------
        contour_mask : ndarray
            Dilatied contour mask.

        """

        dilationimg = dilation(contour_skeleton, square(dilation_parameter))

        contour_mask = dilationimg * mask_without_holes

        return contour_mask

    def get_cell_filled_mask(
        RawRegionImg,
        region_area,
        cell_region_opening_factor,
        cell_region_closing_factor,
    ):
        """
        Return the stand alone single filled cell mask without inner holes.

        Parameters
        ----------
        RawRegionImg : ndarray
            Original region image.
        region_area : TYPE
            Area of binary whole cell mask.
        cell_region_opening_factor : TYPE
            Number used for opening.
        cell_region_closing_factor : TYPE
            Number used for closing.

        Returns
        -------
        filled_mask_bef: ndarray
            Sstand alone single filled cell mask without inner holes.

        """

        # ---------------------------------------------------Get binary cell image baseed on expanded current region image-------------------------------------------------
        RawRegionImg = denoise_tv_chambolle(RawRegionImg, weight=0.01)
        binary_adaptive_block_size = region_area * 0.3
        if (binary_adaptive_block_size % 2) == 0:
            binary_adaptive_block_size += 1
        #        thresh_regionbef = threshold_otsu(RawRegionImg)
        thresh_regionbef = threshold_local(
            RawRegionImg, binary_adaptive_block_size, offset=0
        )
        expanded_binary_region_bef = np.where(RawRegionImg >= thresh_regionbef, 1, 0)

        binarymask_bef = opening(
            expanded_binary_region_bef, square(int(cell_region_opening_factor))
        )
        expanded_binary_region_bef = closing(
            binarymask_bef, square(int(cell_region_closing_factor))
        )

        # ---------------------------------------------------fill in the holes, prepare for contour recognition-----------------------------------------------------------
        seed_bef = np.copy(expanded_binary_region_bef)
        seed_bef[1:-1, 1:-1] = expanded_binary_region_bef.max()
        mask_bef = expanded_binary_region_bef

        filled_mask_bef = reconstruction(
            seed_bef, mask_bef, method="erosion"
        )  # The binary mask with filling holes

        # Calculate the background
        MeanIntensity_Background = np.mean(RawRegionImg[np.where(filled_mask_bef == 0)])
        """ MeanIntensity_Background is not accurate!!!
        """
        MeanIntensity_Background = 0
        # ----------------------------------------------------Clean up parts that don't belong to cell of interest---------------------------------------
        SubCellClearUpSize = int(
            region_area * 0.35
        )  # Assume that trash parts won't take up 35% of the whole cell boundbox area
        #        print(region_area)
        IndividualCellCleared = filled_mask_bef.copy()

        clear_border(IndividualCellCleared)
        # label image regions, prepare for regionprops
        IndividualCell_label_image = label(IndividualCellCleared)

        for subcellregion in regionprops(
            IndividualCell_label_image, intensity_image=RawRegionImg.copy()
        ):

            if (
                subcellregion.area < SubCellClearUpSize
            ):  # Clean parts that are smaller than SubCellClearUpSize, which should result in only one main part left.

                for EachsubcellregionCoords in subcellregion.coords:
                    #                                print(EachsubcellregionCoords.shape)
                    filled_mask_bef[
                        EachsubcellregionCoords[0], EachsubcellregionCoords[1]
                    ] = 0
        # ------------------------------------------------------------------------------------------------------------------------------------------------

        return filled_mask_bef, MeanIntensity_Background

    def smoothing_filled_mask(
        RawRegionImg, filled_mask_bef, region_area, threshold_factor
    ):
        """
        Given the cell filled mask, smooth the egde by convolution.

        Parameters
        ----------
        RawRegionImg : ndarray
            Raw input image.
        filled_mask_bef : ndarray
            Filled mask of cell.
        region_area : int
            Whole cell boundbox area, used to clean up parts that don't belong to cell of interest.
        threshold_factor : float
             The threshold used to shrink the mask.

        Returns
        -------
        filled_mask_reconstructed : ndarray

        """
        # Shrink the image a bit.
        #        filled_mask_bef = binary_erosion(filled_mask_bef, square(1))
        # Try to smooth the boundary.
        kernel = np.ones((5, 5))
        filled_mask_convolve2d = convolve2d(filled_mask_bef, kernel, mode="same")
        try:
            filled_mask_convolve2d = np.where(
                filled_mask_convolve2d
                >= threshold_otsu(filled_mask_convolve2d) * threshold_factor,
                1,
                0,
            )  # Here higher the threshold a bit to shrink the mask, make sure generated contour doesn't exceed.
        except:
            pass
        # Get rid of little patches.
        #                self.filled_mask_convolve2d = opening(self.filled_mask_convolve2d, square(int(1)))

        # ---------------------------------------------------fill in the holes, prepare for contour recognition-----------------------------------------------------------
        seed_bef = np.copy(filled_mask_convolve2d)
        seed_bef[1:-1, 1:-1] = filled_mask_convolve2d.max()
        mask_bef = filled_mask_convolve2d

        filled_mask_reconstructed = reconstruction(
            seed_bef, mask_bef, method="erosion"
        )  # The binary mask with filling holes
        # ----------------------------------------------------Clean up parts that don't belong to cell of interest---------------------------------------
        SubCellClearUpSize = int(
            region_area * 0.30
        )  # Assume that trash parts won't take up 35% of the whole cell boundbox area
        #                    print('minsize: '+str(SubCellClearUpSize))
        IndividualCellCleared = filled_mask_reconstructed.copy()

        clear_border(IndividualCellCleared)
        # label image regions, prepare for regionprops
        IndividualCell_label_image = label(IndividualCellCleared)

        for subcellregion_convolve2d in regionprops(
            IndividualCell_label_image, intensity_image=RawRegionImg.copy()
        ):

            if subcellregion_convolve2d.area < SubCellClearUpSize:

                for EachsubcellregionCoords in subcellregion_convolve2d.coords:
                    #                                print(EachsubcellregionCoords.shape)
                    filled_mask_reconstructed[
                        EachsubcellregionCoords[0], EachsubcellregionCoords[1]
                    ] = 0
        # ------------------------------------------------------------------------------------------------------------------------------------------------
        return filled_mask_reconstructed

    def get_Skeletonized_contour(
        image,
        RegionProposalMask,
        smallest_size,
        contour_thres,
        contour_dilationparameter,
        cell_region_opening_factor,
        cell_region_closing_factor,
        scanning_voltage,
        points_per_contour,
        sampling_rate,
    ):
        """
        # =============================================================================
        #         Get the skeletonized contour of the cell for automated contour scanning.
        # -- RegionProposalMask: the binary mask for region iterative analysis.
        # -- smallest_size: cells size below this number are ignored.
        # -- lowest_region_intensity: cells with mean region intensity below this are ignored.
        # -- contour_thres: threshold for contour recognizition.
        # -- contour_dilationparameter: the dilation degree applied when doing inward contour dilation for thicker menbrane area.
        # -- cell_region_opening_factor: degree of opening operation on individual cell mask.
        # -- cell_region_closing_factor: degree of closing operation on individual cell mask.
        # -- scanning_voltage: The scanning voltage of input image.
        # -- points_per_contour: desired number of points in contour routine.
        # -- sampling_rate: sampling rate for contour scanning.
        # =============================================================================
        """
        cleared = RegionProposalMask.copy()
        clear_border(cleared)
        # label image regions, prepare for regionprops
        label_image = label(cleared)

        CellSequenceInRegion = 0
        CellSkeletonizedContourDict = {}
        #        dtype = [('No.', int), ('Mean intensity', float), ('Mean intensity in contour', float), ('Contour soma ratio', float)]

        for region in regionprops(
            label_image, intensity_image=image
        ):  # USE first image in stack before perfusion as template

            # skip small images
            if region.area > smallest_size:

                # draw rectangle around segmented coins
                minr, minc, maxr, maxc = region.bbox

                # region_mean_intensity = region.mean_intensity #mean intensity of the region, 0 pixels in label are omitted.

                # Based on the boundingbox for each cell from first image in the stack, raw image of slightly larger region is extracted from each round.
                RawRegionImg = image[
                    max(minr - 4, 0) : min(maxr + 4, image[0].shape[0]),
                    max(minc - 4, 0) : min(maxc + 4, image[0].shape[0]),
                ]  # Raw region image

                RawRegionImg_for_contour = RawRegionImg.copy()

                # ---------Get the cell filled mask-------------
                (
                    filled_mask_bef,
                    MeanIntensity_Background,
                ) = ProcessImage.get_cell_filled_mask(
                    RawRegionImg=RawRegionImg,
                    region_area=region.area,
                    cell_region_opening_factor=cell_region_opening_factor,
                    cell_region_closing_factor=cell_region_closing_factor,
                )

                filled_mask_convolve2d = ProcessImage.smoothing_filled_mask(
                    RawRegionImg,
                    filled_mask_bef=filled_mask_bef,
                    region_area=region.area,
                    threshold_factor=2,
                )

                # Set the edge lines to zero so that we don't have the risk of unclosed contour at the edge of image.
                if minr == 0 or minc == 0:
                    filled_mask_convolve2d[0, :] = False
                    filled_mask_convolve2d[:, 0] = False
                if maxr == image[0].shape[0] or maxc == image[0].shape[0]:
                    filled_mask_convolve2d[
                        filled_mask_convolve2d.shape[0] - 1, :
                    ] = False
                    filled_mask_convolve2d[
                        :, filled_mask_convolve2d.shape[1] - 1
                    ] = False

                # Find contour along filled image
                contour_mask_thin_line = ProcessImage.findContour(
                    filled_mask_convolve2d,
                    RawRegionImg_for_contour.copy(),
                    contour_thres,
                )
                #                plt.figure()
                #                plt.imshow(contour_mask_thin_line)
                #                plt.show()
                # after here intensityimage_intensity is changed from contour labeled with number 5 to binary image
                #                contour_mask_of_cell = imageanalysistoolbox.inward_mask_dilation(contour_mask_thin_line.copy() ,filled_mask_convolve2d, contour_dilationparameter)
                # --------------------------------------------------------------
                #                print(len(np.where(contour_mask_thin_line == 1)[0]))
                if len(np.where(contour_mask_thin_line == 1)[0]) > 0:
                    # -------------------Sorting and filtering----------------------
                    clockwise_sorted_raw_trace = ProcessImage.sort_index_clockwise(
                        contour_mask_thin_line
                    )
                    [
                        X_routine,
                        Y_routine,
                    ], filtered_cellmap = ProcessImage.tune_contour_routine(
                        contour_mask_thin_line,
                        clockwise_sorted_raw_trace,
                        filtering_kernel=1.5,
                    )
                    # --------------------------------------------------------------

                    # ----------Put contour image back to original image.-----------
                    ContourFullFOV = np.zeros((image.shape[0], image.shape[1]))
                    ContourFullFOV[
                        max(minr - 4, 0) : min(maxr + 4, image[0].shape[0]),
                        max(minc - 4, 0) : min(maxc + 4, image[0].shape[0]),
                    ] = filtered_cellmap.copy()

                    X_routine = X_routine + max(minr - 4, 0)
                    Y_routine = Y_routine + max(minc - 4, 0)
                    # --------------------------------------------------------------

                    figure, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10))
                    ax1.imshow(ContourFullFOV, cmap=plt.cm.gray)
                    ax2.imshow(filtered_cellmap * 2 + RawRegionImg, cmap=plt.cm.gray)
                    #                ax2.imshow(ContourFullFOV*2+image, cmap = plt.cm.gray)
                    #                ax2.imshow(filled_mask_convolve2d, cmap = plt.cm.gray)
                    #                figure.tight_layout()
                    plt.show()

                    # ------------Organize for Ni-daq execution---------------------
                    voltage_contour_routine_X = (
                        X_routine / ContourFullFOV.shape[0]
                    ) * scanning_voltage * 2 - scanning_voltage
                    voltage_contour_routine_Y = (
                        Y_routine / ContourFullFOV.shape[1]
                    ) * scanning_voltage * 2 - scanning_voltage

                    # --------------interpolate to get 500 points-------------------
                    x_axis = np.arange(0, len(voltage_contour_routine_X))
                    f_x = interpolate.interp1d(
                        x_axis, voltage_contour_routine_X, kind="cubic"
                    )
                    newx = np.linspace(
                        x_axis.min(), x_axis.max(), num=points_per_contour
                    )
                    X_interpolated = f_x(newx)

                    y_axis = np.arange(0, len(voltage_contour_routine_Y))
                    f_y = interpolate.interp1d(
                        y_axis, voltage_contour_routine_Y, kind="cubic"
                    )
                    newy = np.linspace(
                        y_axis.min(), y_axis.max(), num=points_per_contour
                    )
                    Y_interpolated = f_y(newy)

                    # -----------speed and accelation check-------------------------
                    #                contour_x_speed = np.diff(X_interpolated)/time_gap
                    #                contour_y_speed = np.diff(Y_interpolated)/time_gap
                    time_gap = 1 / sampling_rate
                    contour_x_acceleration = (
                        np.diff(X_interpolated, n=2) / time_gap ** 2
                    )
                    contour_y_acceleration = (
                        np.diff(Y_interpolated, n=2) / time_gap ** 2
                    )

                    AccelerationGalvo = (
                        1.54 * 10 ** 8
                    )  # Maximum acceleration of galvo mirror in volt/s^2
                    if AccelerationGalvo < np.amax(abs(contour_x_acceleration)):
                        print(np.amax(abs(contour_x_acceleration)))
                    if AccelerationGalvo < np.amax(abs(contour_y_acceleration)):
                        print(np.amax(abs(contour_y_acceleration)))

                    X_interpolated = np.around(X_interpolated, decimals=3)
                    Y_interpolated = np.around(Y_interpolated, decimals=3)

                    ContourArray_forDaq = np.vstack((X_interpolated, Y_interpolated))

                    CellSkeletonizedContourDict[
                        "DaqArray_cell{}".format(CellSequenceInRegion)
                    ] = ContourArray_forDaq
                    CellSkeletonizedContourDict[
                        "ContourMap_cell{}".format(CellSequenceInRegion)
                    ] = ContourFullFOV
                    CellSequenceInRegion += 1
                    # --------------------------------------------------------------

        return CellSkeletonizedContourDict

    def sort_index_clockwise(cellmap):
        """
        Given the binary contour, sort the index so that they are in clockwise sequence for further contour scanning.

        Parameters
        ----------
        cellmap : ndarray
            Binary contour skeleton.

        Returns
        -------
        result : ndarray
            In clockwise sequence.

        """

        rawindexlist = list(zip(np.where(cellmap == 1)[0], np.where(cellmap == 1)[1]))
        rawindexlist.sort()

        cclockwiselist = rawindexlist[0:1]  # first point in clockwise direction
        clockwiselist = rawindexlist[1:2]  # first point in counter clockwise direction
        # reverse the above assignment depending on how first 2 points relate
        if rawindexlist[1][1] > rawindexlist[0][1]:
            clockwiselist = rawindexlist[1:2]
            cclockwiselist = rawindexlist[0:1]

        coordstorage = rawindexlist[2:]
        #        print(len(rawindexlist))
        timeout = time.time()
        while len(clockwiselist + cclockwiselist) != len(rawindexlist):
            for (
                p
            ) in (
                coordstorage
            ):  # Try one by one from coords dump until find one that is right next to existing clockwise or counter clockwise liste.
                # append to the list to which the next point is closest
                x_last_clockwise = clockwiselist[-1][0]
                y_last_clockwise = clockwiselist[-1][1]
                x_last_cclockwise = cclockwiselist[-1][0]
                y_last_cclockwise = cclockwiselist[-1][1]
                #                if (x_last_clockwise-p[0])**2+(y_last_clockwise-p[1])**2 == 1 and \
                #                ((x_last_clockwise-p[0])**2+(y_last_clockwise-p[1])**2) < ((x_last_cclockwise-p[0])**2+(y_last_cclockwise-p[1])**2):
                #                    clockwiselist.append(p)
                #                    coordstorage.remove(p)
                if (x_last_clockwise - p[0]) ** 2 + (
                    y_last_clockwise - p[1]
                ) ** 2 <= 2 and (
                    (x_last_clockwise - p[0]) ** 2 + (y_last_clockwise - p[1]) ** 2
                ) <= (
                    (x_last_cclockwise - p[0]) ** 2 + (y_last_cclockwise - p[1]) ** 2
                ):
                    clockwiselist.append(p)
                    coordstorage.remove(p)
                    break
                elif (x_last_cclockwise - p[0]) ** 2 + (
                    y_last_cclockwise - p[1]
                ) ** 2 <= 2 and (
                    (x_last_clockwise - p[0]) ** 2 + (y_last_clockwise - p[1]) ** 2
                ) > (
                    (x_last_cclockwise - p[0]) ** 2 + (y_last_cclockwise - p[1]) ** 2
                ):
                    #                    print((cclockwiselist[-1][0]-p[0])**2+(cclockwiselist[-1][1]-p[1])**2)
                    #                    print('cc')
                    cclockwiselist.append(p)
                    coordstorage.remove(p)
                    break
            # If clockwise and counter clockwise meet each other
            if (
                len(clockwiselist + cclockwiselist) > 10
                and (x_last_clockwise - x_last_cclockwise) ** 2
                + (y_last_clockwise - y_last_cclockwise) ** 2
                <= 2
            ):
                break
            # If we have a situation like this at the end of enclosure:
            #  0  0  1
            #  0  1  1
            #  1  0  0
            if (
                len(clockwiselist + cclockwiselist) > 10
                and (x_last_clockwise - x_last_cclockwise) ** 2
                + (y_last_clockwise - y_last_cclockwise) ** 2
                == 5
            ):
                if (cclockwiselist[-2][0] - clockwiselist[-1][0]) ** 2 + (
                    cclockwiselist[-2][1] - clockwiselist[-1][1]
                ) ** 2 == 2:
                    cclockwiselist.remove(cclockwiselist[-1])
                    break

            if time.time() > timeout + 2:
                print("timeout")
                break
        #        print(clockwiselist[-1])
        #        print(cclockwiselist[-1])
        #        print(p)
        print(coordstorage)
        cclockwiselist.reverse()
        result = clockwiselist + cclockwiselist

        return result

    def tune_contour_routine(cellmap, clockwise_sorted_raw_trace, filtering_kernel):
        """
        # =============================================================================
        #  Given the clockwise sorted binary contour, interploate and filter for further contour scanning.
        # =============================================================================
        """
        Unfiltered_contour_routine_X = np.array([])
        Unfiltered_contour_routine_Y = np.array([])
        for rawcoord in clockwise_sorted_raw_trace:
            Unfiltered_contour_routine_X = np.append(
                Unfiltered_contour_routine_X, rawcoord[0]
            )
            Unfiltered_contour_routine_Y = np.append(
                Unfiltered_contour_routine_Y, rawcoord[1]
            )

        # filtering and show filtered contour
        #        X_routine = medfilt(Unfiltered_contour_routine_X, kernel_size=filtering_kernel)
        #        Y_routine = medfilt(Unfiltered_contour_routine_Y, kernel_size=filtering_kernel)
        X_routine = gaussian_filter1d(
            Unfiltered_contour_routine_X, sigma=filtering_kernel
        )
        Y_routine = gaussian_filter1d(
            Unfiltered_contour_routine_Y, sigma=filtering_kernel
        )

        filtered_cellmap = np.zeros((cellmap.shape[0], cellmap.shape[1]))
        for i in range(len(X_routine)):
            filtered_cellmap[int(X_routine[i]), int(Y_routine[i])] = 1

        return [X_routine, Y_routine], filtered_cellmap

    def mask_to_contourScanning_DAQsignals(
        filled_mask,
        OriginalImage,
        scanning_voltage,
        points_per_contour,
        sampling_rate,
        repeats=1,
    ):
        """
        # =============================================================================
        #  Given the binary mask which ONLY covers cell of interest and original image,
        #  generate the voltage signals to NI-DAQ for one contour scanning.
        #
        #  -- filled_mask: The filled binary mask which ONLY covers cell of interest.
        #     Refer to outputs from func:get_cell_filled_mask and func:smoothing_filled_mask.
        #  -- OriginalImage: Raw image.
        #  -- scanning_voltage: The scanning voltage of input image.
        #  -- points_per_contour: desired number of points in contour routine.
        #  -- sampling_rate: sampling rate for contour scanning.
        # =============================================================================
        """
        AccelerationGalvo = (
            1.54 * 10 ** 8
        )  # Maximum acceleration of galvo mirror in volt/s^2

        # Find contour along filled image
        contour_mask_thin_line = ProcessImage.findContour(
            filled_mask, OriginalImage.copy(), threshold=0.001
        )
        # --------------------------------------------------------------
        if len(np.where(contour_mask_thin_line == 1)[0]) > 0:
            # -------------------Sorting and filtering----------------------
            clockwise_sorted_raw_trace = ProcessImage.sort_index_clockwise(
                contour_mask_thin_line
            )
            [
                X_routine,
                Y_routine,
            ], filtered_cellmap = ProcessImage.tune_contour_routine(
                contour_mask_thin_line, clockwise_sorted_raw_trace, filtering_kernel=1.5
            )
            # --------------------------------------------------------------

            # ------------Organize for Ni-daq execution---------------------
            voltage_contour_routine_X = (
                X_routine / OriginalImage.shape[0]
            ) * scanning_voltage * 2 - scanning_voltage
            voltage_contour_routine_Y = (
                Y_routine / OriginalImage.shape[1]
            ) * scanning_voltage * 2 - scanning_voltage

            # -----interpolate to get desired number of points in one contour---
            x_axis = np.arange(0, len(voltage_contour_routine_X))
            f_x = interpolate.interp1d(x_axis, voltage_contour_routine_X, kind="cubic")
            newx = np.linspace(x_axis.min(), x_axis.max(), num=points_per_contour)
            X_interpolated = f_x(newx)

            y_axis = np.arange(0, len(voltage_contour_routine_Y))
            f_y = interpolate.interp1d(y_axis, voltage_contour_routine_Y, kind="cubic")
            newy = np.linspace(y_axis.min(), y_axis.max(), num=points_per_contour)
            Y_interpolated = f_y(newy)

            # ---------------speed and accelation check-------------------------
            time_gap = 1 / sampling_rate
            contour_x_acceleration = np.diff(X_interpolated, n=2) / time_gap ** 2
            contour_y_acceleration = np.diff(Y_interpolated, n=2) / time_gap ** 2

            if AccelerationGalvo < np.amax(abs(contour_x_acceleration)):
                print("Danger! Xmax: {}".format(np.amax(abs(contour_x_acceleration))))
            if AccelerationGalvo < np.amax(abs(contour_y_acceleration)):
                print("Danger! Ymax: {}".format(np.amax(abs(contour_y_acceleration))))

            X_interpolated = np.tile(np.around(X_interpolated, decimals=3), repeats)
            Y_interpolated = np.tile(np.around(Y_interpolated, decimals=3), repeats)

            # Pure numerical np arrays need to be converted to structured array, with 'Sepcification' field being the channel name.
            tp_analog = np.dtype(
                [("Waveform", float, (len(X_interpolated),)), ("Sepcification", "U20")]
            )
            ContourArray_forDaq = np.zeros(2, dtype=tp_analog)
            ContourArray_forDaq[0] = np.array(
                [(X_interpolated, "galvos_X_contour")], dtype=tp_analog
            )
            ContourArray_forDaq[1] = np.array(
                [(Y_interpolated, "galvos_Y_contour")], dtype=tp_analog
            )

            # ContourArray_forDaq = np.vstack((X_interpolated,Y_interpolated))
        else:
            print("Error: no contour found")
            return

        return ContourArray_forDaq

    #%%
    # =============================================================================
    #     ROI and mask generation, DMD related
    # =============================================================================
    def CreateBinaryMaskFromRoiCoordinates(
        list_of_rois,
        fill_contour=False,
        contour_thickness=1,
        mask_resolution=(2048, 2048),
        invert_mask=False,
    ):
        """
        Creating a binary mask using a set of vertices defining roi's. This function
        is written for the purpose of creating DMD masks.

        param list_of_rois: list of numpy arrays, that contain vertices coordinates
                            defining a roi. Example with 2 square roi's:
                                list_of_rois = [np.array((0,0), (1,0), (0,1), (1,1)), np.array((2,2), (2,3), (3,2), (3,3))]
        param fill_contour: if False create contour mask, if True create filled shape mask
        param contour_thickness: only applies when fill_contour is False
        param mask_resolution: size of the mask, default is camera output resolution, for DMD use (768,1024)
        param invert_mask: invert binary mask, meaning 1 and 0 interchange
        """

        mask = np.zeros(mask_resolution)

        for roi in list_of_rois:
            if fill_contour:
                mask += polygon2mask(mask_resolution, roi)
            else:
                mask[polygon_perimeter(roi[:, 0], roi[:, 1], mask_resolution)] = 1

                for _ in range(contour_thickness):
                    mask += binary_dilation(binary_dilation(mask))

        # Make sure the mask is binary
        mask = (mask > 0).astype(int)

        if invert_mask:
            mask = 1 - mask

        return mask

    def ROIitem2Mask(
        roi_list,
        fill_contour=True,
        contour_thickness=1,
        mask_resolution=(1024, 768),
        invert_mask=False,
    ):
        """
        Create binary mask from roi items from pyqtgraph

        Parameters
        ----------
        image_shape : tuple of size 2.
            The shape of the mask.
        polygon : array_like.
            The polygon coordinates of shape (N, 2) where N is
            the number of points.

        Returns
        -------
        mask : 2-D ndarray of type 'bool'.
            The mask that corresponds to the input polygon.

        """
        list_of_rois = []
        Width = int(mask_resolution[0])
        Height = int(mask_resolution[1])

        mask = np.zeros((Width, Height))

        if type(roi_list) is list:
            for roi in roi_list:
                roi_handle_positions = roi.getLocalHandlePositions()
                #                print(roi.getLocalHandlePositions())
                num_vertices = len(roi_handle_positions)
                vertices = np.zeros([num_vertices, 2])

                for idx, vertex in enumerate(roi_handle_positions):
                    vertices[idx, :] = np.array([vertex[1].y(), vertex[1].x()])
                #
                list_of_rois.append(vertices)

                for roi in list_of_rois:
                    if fill_contour:
                        mask += polygon2mask((Width, Height), roi)
                    else:
                        mask[
                            polygon_perimeter(roi[:, 0], roi[:, 1], mask_resolution)
                        ] = 1

                        for _ in range(contour_thickness):
                            mask += binary_dilation(binary_dilation(mask))

        elif type(roi_list) is dict:
            for roikey in roi_list:
                roi = roi_list[roikey]
                roi_handle_positions = roi.getLocalHandlePositions()
                #                print(roi.getLocalHandlePositions())
                num_vertices = len(roi_handle_positions)
                vertices = np.zeros([num_vertices, 2])

                for idx, vertex in enumerate(roi_handle_positions):
                    vertices[idx, :] = np.array([vertex[1].y(), vertex[1].x()])
                #
                list_of_rois.append(vertices)

                for roi in list_of_rois:
                    if fill_contour:
                        mask += polygon2mask((Width, Height), roi)
                    else:
                        mask[
                            polygon_perimeter(roi[:, 0], roi[:, 1], mask_resolution)
                        ] = 1

                        for _ in range(contour_thickness):
                            mask += binary_dilation(binary_dilation(mask))

        return mask

    def ROIitem2Vertices(roi_items_list):
        """
        Return vertices from input pyqtgraph roi items

        Parameters
        ----------
        roi_items_list: list of roi items from pyqtgraph.

        Returns
        -------
        list_of_rois: List of vertices np array
            e.g. [np.array([[1,1],[1,2],[2,1]]), #from first roi item
                  np.array([[1,1],[1,2],[2,1]])  #from second roi item
                    ]
        """
        list_of_rois = []

        for roi in roi_items_list:
            roi_handle_positions = roi.getLocalHandlePositions()

            num_vertices = len(roi_handle_positions)
            vertices = np.zeros([num_vertices, 2])

            for idx, vertex in enumerate(roi_handle_positions):
                vertices[idx, :] = np.array([vertex[1].y(), vertex[1].x()])

            list_of_rois.append(vertices)

        return list_of_rois

    def vertices_to_DMD_mask(
        vertices_assemble,
        laser,
        dict_transformations,
        flag_fill_contour=True,
        contour_thickness=1,
        flag_invert_mode=False,
        mask_resolution=(1024, 768),
    ):
        """
        Create binary DMD transformed mask from input vertices

        Parameters
        ----------
        vertices_assemble : np.array of size (n, 2), e.g. np.array([[1,1], [1, 2], [1,3]]),
                            or list of np.array of size 2, e.g. [np.array([1,1]), np.array([2,1])]
            The vertices of the input mask contour.
        laser :
            To which laser the returned DMD mask belongs.

        Returns
        -------
        mask_transformed : 2-D ndarray.
            The transformed mask that corresponds to the input vertices group.
        """
        mask_transformed = {}
        list_of_rois_transformed = []  # list of np.array

        if type(vertices_assemble) is list or type(vertices_assemble) is np.ndarray:

            vertices_assemble = np.asarray(vertices_assemble)

            if "camera-dmd-" + laser in dict_transformations.keys():

                vertices_transformed = ProcessImage.transform(
                    vertices_assemble, dict_transformations["camera-dmd-" + laser]
                )
                list_of_rois_transformed.append(vertices_transformed)
            else:
                list_of_rois_transformed.append(vertices_assemble)
                print("Warning: not registered")

            mask_transformed[laser] = ProcessImage.CreateBinaryMaskFromRoiCoordinates(
                list_of_rois_transformed,
                fill_contour=flag_fill_contour,
                contour_thickness=contour_thickness,
                invert_mask=flag_invert_mode,
            )
            print(mask_transformed[laser].shape)

        return mask_transformed

    def binarymask_to_DMD_mask(
        binary_mask,
        laser,
        dict_transformations,
        flag_fill_contour=True,
        contour_thickness=1,
        flag_invert_mode=False,
        mask_resolution=(1024, 768),
    ):
        """
        First binart mask to contour vertices, then from vertices to transformed vertices then to DMD mask.

        Parameters
        ----------
        binary_mask : TYPE
            DESCRIPTION.
        laser : TYPE
            DESCRIPTION.
        dict_transformations : TYPE
            DESCRIPTION.
        flag_fill_contour : TYPE, optional
            DESCRIPTION. The default is True.
        contour_thickness : TYPE, optional
            DESCRIPTION. The default is 1.
        flag_invert_mode : TYPE, optional
            DESCRIPTION. The default is False.
        mask_resolution : TYPE, optional
            DESCRIPTION. The default is (1024, 768).

        Returns
        -------
        mask_transformed_final : TYPE
            DESCRIPTION.

        """

        mask_transformed_final = np.zeros((mask_resolution[1], mask_resolution[0]))

        contours = find_contours(
            binary_mask, 0.5
        )  # Find iso-valued contours in a 2D array for a given level value.

        for n, contour in enumerate(contours):

            mask_transformed = ProcessImage.vertices_to_DMD_mask(
                contour,
                laser,
                dict_transformations,
                flag_fill_contour=True,
                contour_thickness=1,
                flag_invert_mode=False,
                mask_resolution=(1024, 768),
            )
            print(mask_transformed_final.shape)
            print(mask_transformed[laser].shape)
            mask_transformed_final += mask_transformed[laser]

        return mask_transformed_final

    def transform(r, A):
        """
        This function takes points as input and returns the
        transformed points.

        r = np.array([[1,1], [1, 2], [1,3]])

        """

        if r.ndim == 1:
            Q = ProcessImage.createTransformationMatrix(r)

            if Q is None:
                return

            return np.squeeze(np.reshape(np.dot(Q, A), (-1, 2), order="F"))

        else:
            num_points = r.shape[0]

        transformed_points = np.zeros([num_points, 2])

        for i in range(num_points):

            Q = ProcessImage.createTransformationMatrix(r[i, :])

            if Q is None:
                return

            transformed_points[i, :] = np.squeeze(np.dot(Q, A))
        return np.reshape(transformed_points, (-1, 2), order="F")

    def createTransformationMatrix(q, order=1):
        if len(q.shape) == 1:
            Qx = np.array([1, 0, q[0], q[1]])
            Qy = np.hstack((0, 1, np.zeros(2 * order), q[0], q[1]))

            for i in range(2, order + 1):
                Qx = np.hstack((Qx, q[0] ** i, q[1] ** i))
                Qy = np.hstack((Qy, q[0] ** i, q[1] ** i))

            Qx = np.hstack((Qx, np.zeros(2 * order)))
        else:
            print("Function takes only one point at a time")
            return

        return np.vstack((Qx, Qy))

    #%%
    # =============================================================================
    #     MaskRCNN related
    # =============================================================================
    def convert_for_MaskRCNN(input_img):
        """Convert the image size and bit-depth to make it suitable for MaskRCNN detection.

        Parameters
        ----------
        input_img : 2-D ndarray.
            Input image.

        Returns
        -------
        output_image : 2-D ndarray.
            Converted image after resizing and bit-size adjustment.
        """
        if input_img.shape[0] > 1024 or input_img.shape[1] > 1024:
            resized_img = resize(input_img, [1024, 1024], preserve_range=True).astype(
                input_img.dtype
            )
        else:
            resized_img = input_img

        minval = np.min(resized_img)
        maxval = np.max(resized_img)

        output_image = ((resized_img - minval) / (maxval - minval) * 255).astype(
            np.uint8
        ) + 1

        if len(np.shape(output_image)) == 2:
            output_image = gray2rgb(output_image)

        return output_image

    def retrieveDataFromML(
        image,
        MLresults,
        ImgNameInfor="Not specified",
        add_up_cell_counted_number=0,
        show_each_cell=False,
    ):
        """Given the raw image and ML returned result dictionary, calculate interested parameters from it.

        class_ids = 3: Flat cell
        class_ids = 2: Round cell
        class_ids = 1: Dead cell

        #   Returned structured array fields:
        #   - BoundingBox of cell ROI
        #   - Mean intensity of whole cell area
        #   - Mean intensity of cell membrane part
        #   - Contour soma ratio

        Parameters
        ----------
        image : 2-D ndarray.
            Input image.
        MLresults : Dictionary.
            The returned dictionary from MaskRCNN.
        ImgNameInfor : String.
            Information of input image.
        add_up_cell_counted_number: int.
            Number of cells already counted in round.
        Returns
        -------
        Cell_DataFrame : pd.DataFrame.
            Detail information extracted from MaskRCNN mask from the image, in pandas dataframe format.
        add_up_cell_counted_number: int.
            Number of cells counted, together with previous number from this image.
        """
        ROInumber = len(MLresults["rois"])
        flat_cell_counted_inImage = 0

        total_cells_identified = 0  # All identified cells number

        for eachROI in range(ROInumber):
            if MLresults["class_ids"][eachROI] == 3:
                ROIlist = MLresults["rois"][eachROI]
                CellMask = MLresults["masks"][:, :, eachROI]

                # If image size is larger than 1024X1024, it is resized before processed by MaskRCNN.
                # Here we need to resize the image to match the output mask from MaskRCNN.
                if (
                    image.shape[0] != CellMask.shape[0]
                    or image.shape[1] != CellMask.shape[1]
                ):
                    resized_img = resize(
                        image,
                        [CellMask.shape[0], CellMask.shape[1]],
                        preserve_range=True,
                    ).astype(image.dtype)
                    RawImg_roi = resized_img[
                        ROIlist[0] : ROIlist[2], ROIlist[1] : ROIlist[3]
                    ]  # Raw image in each bounding box
                else:
                    RawImg_roi = image[
                        ROIlist[0] : ROIlist[2], ROIlist[1] : ROIlist[3]
                    ]  # Raw image in each bounding box

                CellMask_roi = CellMask[
                    ROIlist[0] : ROIlist[2], ROIlist[1] : ROIlist[3]
                ]  # Individual cell mask in each bounding box

                # =============================================================
                #             # Find contour along cell mask
                # =============================================================
                cell_contour_mask = closing(
                    ProcessImage.findContour(CellMask_roi, RawImg_roi.copy(), 0.001),
                    square(5),
                )  # Return the binary contour mask in bounding box.
                # after here intensityimage_intensity is changed from contour labeled with number 5 to binary image.

                cell_contour_mask_dilated = ProcessImage.inward_mask_dilation(
                    cell_contour_mask, CellMask_roi, dilation_parameter=8
                )

                # Trim the contour mask
                cell_contour_mask_processed = opening(
                    cell_contour_mask_dilated, square(4)
                )

                if show_each_cell == True:
                    fig, axs = plt.subplots(3)
                    # fig.suptitle('Individual cell mask')
                    axs[0].imshow(RawImg_roi)
                    axs[0].set_title("Cell image")
                    axs[0].set_xticks([])
                    axs[1].imshow(cell_contour_mask_dilated, cmap="gray")
                    axs[1].set_title("Cell contour mask")
                    axs[1].set_xticks([])
                    axs[2].imshow(cell_contour_mask_processed, cmap="gray")
                    axs[2].set_title("Cell contour trimed")
                    axs[2].set_xticks([])
                # -------------Calculate intensity based on masks---------------
                cell_contour_meanIntensity = np.mean(
                    RawImg_roi[np.where(cell_contour_mask_dilated == 1)]
                )  # Mean pixel value of cell membrane.
                cell_area_meanIntensity = np.mean(
                    RawImg_roi[np.where(CellMask_roi == 1)]
                )  # Mean pixel value of whole cell area.

                cell_soma_mask = CellMask_roi - cell_contour_mask_dilated
                cell_soma_meanIntensity = np.mean(
                    RawImg_roi[np.where(cell_soma_mask == 1)]
                )  # Mean pixel value of soma area.
                cell_contourSoma_ratio = round(
                    cell_contour_meanIntensity / cell_soma_meanIntensity, 5
                )  # Calculate the contour/soma intensity ratio.

                boundingbox_info = "minr{}_maxr{}_minc{}_maxc{}".format(
                    ROIlist[0], ROIlist[2], ROIlist[1], ROIlist[3]
                )

                if flat_cell_counted_inImage == 0:
                    Cell_DataFrame = pd.DataFrame(
                        [
                            [
                                ImgNameInfor,
                                boundingbox_info,
                                cell_area_meanIntensity,
                                cell_contour_meanIntensity,
                                cell_contourSoma_ratio,
                            ]
                        ],
                        columns=[
                            "ImgNameInfor",
                            "BoundingBox",
                            "Mean_intensity",
                            "Mean_intensity_in_contour",
                            "Contour_soma_ratio",
                        ],
                        index=["Cell {}".format(add_up_cell_counted_number)],
                    )
                else:
                    Cell_DataFrame_new = pd.DataFrame(
                        [
                            [
                                ImgNameInfor,
                                boundingbox_info,
                                cell_area_meanIntensity,
                                cell_contour_meanIntensity,
                                cell_contourSoma_ratio,
                            ]
                        ],
                        columns=[
                            "ImgNameInfor",
                            "BoundingBox",
                            "Mean_intensity",
                            "Mean_intensity_in_contour",
                            "Contour_soma_ratio",
                        ],
                        index=["Cell {}".format(add_up_cell_counted_number)],
                    )
                    Cell_DataFrame = Cell_DataFrame.append(Cell_DataFrame_new)

                add_up_cell_counted_number += 1
                flat_cell_counted_inImage += 1

                total_cells_identified += 1

            elif MLresults["class_ids"][eachROI] == 2:  # Round cells

                total_cells_identified += 1

        if flat_cell_counted_inImage == 0:
            return pd.DataFrame(), add_up_cell_counted_number, total_cells_identified
        else:
            return Cell_DataFrame, add_up_cell_counted_number, total_cells_identified

    def Register_cells(data_frame_list):
        """
        Trace inidividual cell at different time points based on bounding box
        overlapping from the dataframe list.

        Parameters
        ----------
        data_frame_list : list
            List of dataframes of cells from different time points.

        Returns
        -------
        whole_registered_dataframe : pd.DataFrame
            Registered dataframe.

        """
        # Set the first data frame as starter as it should have most cells.
        whole_registered_dataframe = data_frame_list[0].set_index("Unnamed: 0")

        for previous_dataframe_index in range(len(data_frame_list) - 1):

            if previous_dataframe_index == 0:
                registered_dataframe = ProcessImage.Register_between_dataframes(
                    data_frame_list[previous_dataframe_index].set_index("Unnamed: 0"),
                    data_frame_list[previous_dataframe_index + 1].set_index(
                        "Unnamed: 0"
                    ),
                )
            else:
                registered_dataframe = ProcessImage.Register_between_dataframes(
                    registered_dataframe,
                    data_frame_list[previous_dataframe_index + 1].set_index(
                        "Unnamed: 0"
                    ),
                )

            whole_registered_dataframe = whole_registered_dataframe.join(
                registered_dataframe,
                rsuffix="_round_{}".format(previous_dataframe_index + 1),
            )

        return whole_registered_dataframe

    def Retrieve_boundingbox(bounding_box_str):
        """
        Given the input boundingbox string, return the row/col limits.

        Parameters
        ----------
        bounding_box_str : TYPE
            DESCRIPTION.

        Returns
        -------
        minr_Data : int
            Minimum row index.
        maxr_Data : int
            Maximum row index.
        minc_Data : int
            Minimum col index.
        maxc_Data : int
            Maximum col index.

        """
        minr_Data = int(
            bounding_box_str[
                bounding_box_str.index("minr") + 4 : bounding_box_str.index("_maxr")
            ]
        )
        maxr_Data = int(
            bounding_box_str[
                bounding_box_str.index("maxr") + 4 : bounding_box_str.index("_minc")
            ]
        )
        minc_Data = int(
            bounding_box_str[
                bounding_box_str.index("minc") + 4 : bounding_box_str.index("_maxc")
            ]
        )
        maxc_Data = int(
            bounding_box_str[bounding_box_str.index("maxc") + 4 : len(bounding_box_str)]
        )

        return minr_Data, maxr_Data, minc_Data, maxc_Data

    def Register_between_dataframes(
        dataframe_previous, dataframe_latter, boundingbox_overlapping_thres=0.6
    ):
        """
        Given two dataframs from different time, find back the same cells from latter time point.
        Show NAN instead if fail to trace back the cell.

        Parameters
        ----------
        dataframe_previous : pd.DataFrame
            DataFrame of first time point.
        dataframe_latter : pd.DataFrame
            DataFrame of second time point.
        boundingbox_overlapping_thres : TYPE, optional
            Bounding box verlapping percentage threshold above which will be
            seen as same cell. The default is 0.6.

        Returns
        -------
        registered_dataframe : pd.DataFrame
            Show NAN on row instead if fail to trace back the cell.

        """

        registered_dataframe = pd.DataFrame()

        for (
            index_previous_data_frame,
            row_previous_data_frame,
        ) in dataframe_previous.iterrows():
            # For each flat cell in round
            bounding_box_str_Last_data_frame = row_previous_data_frame["BoundingBox"]
            ImgNameInfor_string = row_previous_data_frame["ImgNameInfor"]

            # Retrieve boundingbox information
            (
                minr_Data_1,
                maxr_Data_1,
                minc_Data_1,
                maxc_Data_1,
            ) = ProcessImage.Retrieve_boundingbox(bounding_box_str_Last_data_frame)

            Area_bbox_Last_data_frame = (maxr_Data_1 - minr_Data_1) * (
                maxc_Data_1 - minc_Data_1
            )

            intersection_area_percentage_list = []
            index_list_same_coordinate = []
            registered_cell_Series_list = []

            # From the image name information, locate rows only from the same coordinate, generate a pd.dataframe
            DataFrame_of_same_coordinate = dataframe_latter[
                dataframe_latter["ImgNameInfor"].str.contains(
                    ImgNameInfor_string[
                        ImgNameInfor_string.index("_R") + 1 : len(ImgNameInfor_string)
                    ]
                )
            ]

            for index_2, row_Data_2 in DataFrame_of_same_coordinate.iterrows():

                bounding_box_str_latter = row_Data_2["BoundingBox"]
                # Retrieve boundingbox information
                (
                    minr_Data_2,
                    maxr_Data_2,
                    minc_Data_2,
                    maxc_Data_2,
                ) = ProcessImage.Retrieve_boundingbox(bounding_box_str_latter)

                Area_bbox_latter_round = (maxr_Data_2 - minr_Data_2) * (
                    maxc_Data_2 - minc_Data_2
                )

                # Overlapping row
                if minr_Data_2 < maxr_Data_1 and maxr_Data_2 > minr_Data_1:
                    intersection_rowNumber = min(
                        (abs(minr_Data_2 - maxr_Data_1), maxr_Data_1 - minr_Data_1)
                    ) - max(maxr_Data_1 - maxr_Data_2, 0)
                else:
                    intersection_rowNumber = 0
                # Overlapping column
                if minc_Data_2 < maxc_Data_1 and maxc_Data_2 > minc_Data_1:
                    intersection_colNumber = min(
                        (abs(minc_Data_2 - maxc_Data_1), maxc_Data_1 - minc_Data_1)
                    ) - max(maxc_Data_1 - maxc_Data_2, 0)
                else:
                    intersection_colNumber = 0

                intersection_Area = intersection_rowNumber * intersection_colNumber
                # Calculate the percentage based on smaller number of intersection over the two.
                intersection_Area_percentage = min(
                    [
                        (intersection_Area / Area_bbox_Last_data_frame),
                        (intersection_Area / Area_bbox_latter_round),
                    ]
                )

                intersection_area_percentage_list.append(intersection_Area_percentage)
                index_list_same_coordinate.append(index_2)

            # Link back cells based on intersection area
            if (
                len(intersection_area_percentage_list) > 0
                and max(intersection_area_percentage_list)
                > boundingbox_overlapping_thres
            ):

                registered_cell_index = index_list_same_coordinate[
                    intersection_area_percentage_list.index(
                        max(intersection_area_percentage_list)
                    )
                ]

                # Get the pd.series from dataframe.
                registered_cell_Series = DataFrame_of_same_coordinate.loc[
                    registered_cell_index
                ].copy()

                # Update the Cell index in the first column.
                registered_cell_Series.name = (
                    dataframe_previous.loc[index_previous_data_frame].copy().name
                )

                # Append the series as dataframe
                registered_dataframe = registered_dataframe.append(
                    registered_cell_Series.to_frame().T
                )

        return registered_dataframe

    def MergeDataFrames(cell_Data_1, cell_Data_2, method="TagLib"):
        """Merge Data frames based on input methods.

        #   'TagLib': Merge tag protein screening round with library screening round.
        #   -In this mode, for each bounding box in the tag round, it will search through every bounding box in library round and find the best match with
        #   -with the most intersection, and then treat them as images from the same cell and merge the two input dataframes.

        Parameters
        ----------
        cell_Data_1, cell_Data_2 : pd.DataFrame.
            Input data from two rounds.
        method : String.
            Merge method.
            'TagLib': for brightness screening.

        Returns
        -------
        Cell_DataFrame_Merged : pd.DataFrame.
            Detail information from merging two input dataframe, with bounding boxes from different rounds overlapping above 60% seen as same cell.
        """

        if method == "TagLib":
            """
            # For the brightness screening, the library brightness is normalized
            # by tag protein brightness.
            """

            cell_Data_1 = cell_Data_1.add_suffix("_Tag")
            cell_Data_2 = cell_Data_2.add_suffix("_Lib")
            cell_merged_num = 0

            print("Start linking cells...")

            # start_time = time.time()
            # # Get the pd.series from first cell.
            # first_pd_data_of_single_cell = self.register_single_cell(("Cell {}".format(0), self.cell_Data_1.iloc[0]))
            # # Make sure that there's content in first pd data.
            # i = 1
            # while type(first_pd_data_of_single_cell) == bool:
            #     first_pd_data_of_single_cell = self.register_single_cell(("Cell {}".format(i), self.cell_Data_1.iloc[0]))
            #     i += 1

            # Cell_DataFrame_Merged = first_pd_data_of_single_cell

            # with concurrent.futures.ProcessPoolExecutor() as executor:
            #     for pd_data_of_single_cell in executor.map(self.register_single_cell, self.cell_Data_1.iterrows()):
            #         if type(pd_data_of_single_cell) != bool:
            #           Cell_DataFrame_Merged = pd.concat((Cell_DataFrame_Merged, pd_data_of_single_cell), axis = 1)

            # end_time = time.time()
            # print("Register takes {}".format(end_time - start_time))

            # Assume that cell_Data_1 is the tag protein dataframe, for each of the cell bounding box,
            # find the one with the most intersection from library dataframe.
            start_time = time.time()
            for index_Data_1, row_Data_1 in cell_Data_1.iterrows():
                # For each flat cell in round
                bounding_box_str_Data_1 = row_Data_1["BoundingBox_Tag"]
                ImgNameInforString_Data1 = row_Data_1["ImgNameInfor_Tag"]
                # Retrieve boundingbox information
                minr_Data_1 = int(
                    bounding_box_str_Data_1[
                        bounding_box_str_Data_1.index("minr")
                        + 4 : bounding_box_str_Data_1.index("_maxr")
                    ]
                )
                maxr_Data_1 = int(
                    bounding_box_str_Data_1[
                        bounding_box_str_Data_1.index("maxr")
                        + 4 : bounding_box_str_Data_1.index("_minc")
                    ]
                )
                minc_Data_1 = int(
                    bounding_box_str_Data_1[
                        bounding_box_str_Data_1.index("minc")
                        + 4 : bounding_box_str_Data_1.index("_maxc")
                    ]
                )
                maxc_Data_1 = int(
                    bounding_box_str_Data_1[
                        bounding_box_str_Data_1.index("maxc")
                        + 4 : len(bounding_box_str_Data_1)
                    ]
                )

                Area_cell_1 = (maxr_Data_1 - minr_Data_1) * (maxc_Data_1 - minc_Data_1)

                intersection_Area_percentage_list = []
                index_list_Data_2 = []

                # Iterate through DataFrame 2 calculating intersection area
                # Get dataframe of same coordinate in dataframe from next round.
                DataFrame_of_same_coordinate_Data2 = cell_Data_2[
                    cell_Data_2["ImgNameInfor_Lib"].str.contains(
                        ImgNameInforString_Data1[
                            ImgNameInforString_Data1.index("_R")
                            + 1 : len(ImgNameInforString_Data1)
                        ]
                    )
                ]

                for (
                    index_2,
                    row_Data_2,
                ) in DataFrame_of_same_coordinate_Data2.iterrows():
                    ImgNameInforString_Data2 = row_Data_2["ImgNameInfor_Lib"]

                    bounding_box_str_Data_2 = row_Data_2["BoundingBox_Lib"]
                    # Retrieve boundingbox information
                    minr_Data_2 = int(
                        bounding_box_str_Data_2[
                            bounding_box_str_Data_2.index("minr")
                            + 4 : bounding_box_str_Data_2.index("_maxr")
                        ]
                    )
                    maxr_Data_2 = int(
                        bounding_box_str_Data_2[
                            bounding_box_str_Data_2.index("maxr")
                            + 4 : bounding_box_str_Data_2.index("_minc")
                        ]
                    )
                    minc_Data_2 = int(
                        bounding_box_str_Data_2[
                            bounding_box_str_Data_2.index("minc")
                            + 4 : bounding_box_str_Data_2.index("_maxc")
                        ]
                    )
                    maxc_Data_2 = int(
                        bounding_box_str_Data_2[
                            bounding_box_str_Data_2.index("maxc")
                            + 4 : len(bounding_box_str_Data_2)
                        ]
                    )

                    Area_cell_2 = (maxr_Data_2 - minr_Data_2) * (
                        maxc_Data_2 - minc_Data_2
                    )

                    # Overlapping row
                    if minr_Data_2 < maxr_Data_1 and maxr_Data_2 > minr_Data_1:
                        intersection_rowNumber = min(
                            (abs(minr_Data_2 - maxr_Data_1), maxr_Data_1 - minr_Data_1)
                        ) - max(maxr_Data_1 - maxr_Data_2, 0)
                    else:
                        intersection_rowNumber = 0
                    # Overlapping column
                    if minc_Data_2 < maxc_Data_1 and maxc_Data_2 > minc_Data_1:
                        intersection_colNumber = min(
                            (abs(minc_Data_2 - maxc_Data_1), maxc_Data_1 - minc_Data_1)
                        ) - max(maxc_Data_1 - maxc_Data_2, 0)
                    else:
                        intersection_colNumber = 0

                    intersection_Area = intersection_rowNumber * intersection_colNumber
                    # Calculate the percentage based on smaller number of intersection over the two.
                    intersection_Area_percentage = min(
                        [
                            (intersection_Area / Area_cell_1),
                            (intersection_Area / Area_cell_2),
                        ]
                    )

                    intersection_Area_percentage_list.append(
                        intersection_Area_percentage
                    )
                    index_list_Data_2.append(index_2)

                if len(intersection_Area_percentage_list) > 0:
                    # Link back cells based on intersection area
                    if max(intersection_Area_percentage_list) > 0.6:
                        # If in DataFrame_2 there's a cell that has a overlapping bounding box, merge and generate a new dataframe.
                        Merge_data2_index = index_list_Data_2[
                            intersection_Area_percentage_list.index(
                                max(intersection_Area_percentage_list)
                            )
                        ]

                        pd_data_of_single_cell = pd.concat(
                            (
                                cell_Data_1.loc[index_Data_1],
                                cell_Data_2.loc[Merge_data2_index],
                            ),
                            axis=0,
                        )

                        # Add the lib/tag brightness ratio
                        Lib_Tag_ratio = pd.DataFrame(
                            [
                                pd_data_of_single_cell.loc[
                                    "Mean_intensity_in_contour_Lib"
                                ]
                                / pd_data_of_single_cell.loc[
                                    "Mean_intensity_in_contour_Tag"
                                ]
                            ],
                            index=["Lib_Tag_contour_ratio"],
                        )

                        pd_data_of_single_cell = pd.concat(
                            (pd_data_of_single_cell, Lib_Tag_ratio), axis=0
                        )
                        pd_data_of_single_cell.rename(
                            columns={0: "Cell {}".format(cell_merged_num)}, inplace=True
                        )  # Rename the column name, which is the index name after T.

                        if cell_merged_num == 0:
                            Cell_DataFrame_Merged = pd_data_of_single_cell
                        else:
                            Cell_DataFrame_Merged = pd.concat(
                                (Cell_DataFrame_Merged, pd_data_of_single_cell), axis=1
                            )
                        cell_merged_num += 1

            end_time = time.time()
            print("Register takes {}".format(end_time - start_time))
            Cell_DataFrame_Merged = Cell_DataFrame_Merged.T
            print("Cell_DataFrame_Merged.")

        # =====================================================================
        elif method == "Kcl":
            """
            # There are two situatiions here, one is simply with absolute intenesity,
            # the other one is with lib/tag ration in the excel, both have different
            # field names, and the final ration is done differently.
            # Bounding box tracing is based on both tag fluorescence images.
            """

            cell_Data_1 = cell_Data_1.add_suffix("_EC")
            cell_Data_2 = cell_Data_2.add_suffix("_KC")
            cell_merged_num = 0

            print("Start linking cells...")
            start_time = time.time()

            for index_Data_1, row_Data_1 in cell_Data_1.iterrows():
                # For each flat cell in round
                try:
                    # For absolute intensity
                    bounding_box_str_Data_1 = row_Data_1["BoundingBox_EC"]
                    ImgNameInforString_Data1 = row_Data_1["ImgNameInfor_EC"]
                except:
                    # For ratio registration
                    bounding_box_str_Data_1 = row_Data_1["BoundingBox_Tag_EC"]
                    ImgNameInforString_Data1 = row_Data_1["ImgNameInfor_Tag_EC"]

                # Retrieve boundingbox information
                minr_Data_1 = int(
                    bounding_box_str_Data_1[
                        bounding_box_str_Data_1.index("minr")
                        + 4 : bounding_box_str_Data_1.index("_maxr")
                    ]
                )
                maxr_Data_1 = int(
                    bounding_box_str_Data_1[
                        bounding_box_str_Data_1.index("maxr")
                        + 4 : bounding_box_str_Data_1.index("_minc")
                    ]
                )
                minc_Data_1 = int(
                    bounding_box_str_Data_1[
                        bounding_box_str_Data_1.index("minc")
                        + 4 : bounding_box_str_Data_1.index("_maxc")
                    ]
                )
                maxc_Data_1 = int(
                    bounding_box_str_Data_1[
                        bounding_box_str_Data_1.index("maxc")
                        + 4 : len(bounding_box_str_Data_1)
                    ]
                )

                Area_cell_1 = (maxr_Data_1 - minr_Data_1) * (maxc_Data_1 - minc_Data_1)

                intersection_Area_percentage_list = []
                index_list_Data_2 = []

                # Iterate through DataFrame 2 calculating intersection area
                # Get dataframe of same coordinate in dataframe from next round.
                try:
                    DataFrame_of_same_coordinate_Data2 = cell_Data_2[
                        cell_Data_2["ImgNameInfor_KC"].str.contains(
                            ImgNameInforString_Data1[
                                ImgNameInforString_Data1.index("_R")
                                + 1 : len(ImgNameInforString_Data1)
                            ]
                        )
                    ]
                except:
                    DataFrame_of_same_coordinate_Data2 = cell_Data_2[
                        cell_Data_2["ImgNameInfor_Tag_KC"].str.contains(
                            ImgNameInforString_Data1[
                                ImgNameInforString_Data1.index("_R")
                                + 1 : len(ImgNameInforString_Data1)
                            ]
                        )
                    ]

                for (
                    index_2,
                    row_Data_2,
                ) in DataFrame_of_same_coordinate_Data2.iterrows():

                    # ImgNameInforString_Data2 = row_Data_2['ImgNameInfor_KC']
                    try:
                        bounding_box_str_Data_2 = row_Data_2["BoundingBox_KC"]
                    except:
                        bounding_box_str_Data_2 = row_Data_2["BoundingBox_Tag_KC"]
                    # Retrieve boundingbox information
                    minr_Data_2 = int(
                        bounding_box_str_Data_2[
                            bounding_box_str_Data_2.index("minr")
                            + 4 : bounding_box_str_Data_2.index("_maxr")
                        ]
                    )
                    maxr_Data_2 = int(
                        bounding_box_str_Data_2[
                            bounding_box_str_Data_2.index("maxr")
                            + 4 : bounding_box_str_Data_2.index("_minc")
                        ]
                    )
                    minc_Data_2 = int(
                        bounding_box_str_Data_2[
                            bounding_box_str_Data_2.index("minc")
                            + 4 : bounding_box_str_Data_2.index("_maxc")
                        ]
                    )
                    maxc_Data_2 = int(
                        bounding_box_str_Data_2[
                            bounding_box_str_Data_2.index("maxc")
                            + 4 : len(bounding_box_str_Data_2)
                        ]
                    )

                    Area_cell_2 = (maxr_Data_2 - minr_Data_2) * (
                        maxc_Data_2 - minc_Data_2
                    )

                    # Overlapping row
                    if minr_Data_2 < maxr_Data_1 and maxr_Data_2 > minr_Data_1:
                        intersection_rowNumber = min(
                            (abs(minr_Data_2 - maxr_Data_1), maxr_Data_1 - minr_Data_1)
                        ) - max(maxr_Data_1 - maxr_Data_2, 0)
                    else:
                        intersection_rowNumber = 0
                    # Overlapping column
                    if minc_Data_2 < maxc_Data_1 and maxc_Data_2 > minc_Data_1:
                        intersection_colNumber = min(
                            (abs(minc_Data_2 - maxc_Data_1), maxc_Data_1 - minc_Data_1)
                        ) - max(maxc_Data_1 - maxc_Data_2, 0)
                    else:
                        intersection_colNumber = 0

                    intersection_Area = intersection_rowNumber * intersection_colNumber
                    # Calculate the percentage based on smaller number of intersection over the two.
                    intersection_Area_percentage = min(
                        [
                            (intersection_Area / Area_cell_1),
                            (intersection_Area / Area_cell_2),
                        ]
                    )

                    intersection_Area_percentage_list.append(
                        intersection_Area_percentage
                    )
                    index_list_Data_2.append(index_2)

                if len(intersection_Area_percentage_list) > 0:
                    # Link back cells based on intersection area
                    if max(intersection_Area_percentage_list) > 0.6:
                        # If in DataFrame_2 there's a cell that has a overlapping bounding box, merge and generate a new dataframe.
                        Merge_data2_index = index_list_Data_2[
                            intersection_Area_percentage_list.index(
                                max(intersection_Area_percentage_list)
                            )
                        ]

                        pd_data_of_single_cell = pd.concat(
                            (
                                cell_Data_1.loc[index_Data_1],
                                cell_Data_2.loc[Merge_data2_index],
                            ),
                            axis=0,
                        )

                        # Add the lib/tag brightness ratio
                        if (
                            "Mean_intensity_in_contour_KC"
                            in pd_data_of_single_cell.index
                        ):
                            # For absolute intensity
                            # For ones with lib/tag ratio, it will have 'Mean_intensity_in_contour_Lib_KC' field instead.
                            Kcl_Lib_Tag_ratio = pd.DataFrame(
                                [
                                    pd_data_of_single_cell.loc[
                                        "Mean_intensity_in_contour_KC"
                                    ]
                                    / pd_data_of_single_cell.loc[
                                        "Mean_intensity_in_contour_EC"
                                    ]
                                ],
                                index=["KC_EC_Mean_intensity_in_contour_ratio"],
                            )

                            pd_data_of_single_cell = pd.concat(
                                (pd_data_of_single_cell, Kcl_Lib_Tag_ratio), axis=0
                            )
                        else:
                            # For lib/tag KC/EC ratio
                            Kcl_LibTag_contour_ratio = pd.DataFrame(
                                [
                                    pd_data_of_single_cell.loc[
                                        "Lib_Tag_contour_ratio_KC"
                                    ]
                                    / pd_data_of_single_cell.loc[
                                        "Lib_Tag_contour_ratio_EC"
                                    ]
                                ],
                                index=["KC_EC_LibTag_contour_ratio"],
                            )
                            Kcl_Lib_Tag_ratio = pd.DataFrame(
                                [
                                    pd_data_of_single_cell.loc[
                                        "Mean_intensity_in_contour_Lib_KC"
                                    ]
                                    / pd_data_of_single_cell.loc[
                                        "Mean_intensity_in_contour_Lib_EC"
                                    ]
                                ],
                                index=["KC_EC_Mean_intensity_in_contour_ratio"],
                            )

                            pd_data_of_single_cell = pd.concat(
                                (pd_data_of_single_cell, Kcl_Lib_Tag_ratio), axis=0
                            )
                            pd_data_of_single_cell = pd.concat(
                                (pd_data_of_single_cell, Kcl_LibTag_contour_ratio),
                                axis=0,
                            )

                        pd_data_of_single_cell.rename(
                            columns={0: "Cell {}".format(cell_merged_num)}, inplace=True
                        )  # Rename the column name, which is the index name after T.

                        if cell_merged_num == 0:
                            Cell_DataFrame_Merged = pd_data_of_single_cell
                        else:
                            Cell_DataFrame_Merged = pd.concat(
                                (Cell_DataFrame_Merged, pd_data_of_single_cell), axis=1
                            )
                        cell_merged_num += 1

            end_time = time.time()
            print("Register takes {}".format(end_time - start_time))
            Cell_DataFrame_Merged = Cell_DataFrame_Merged.T
            print("Cell_DataFrame_Merged.")

        return Cell_DataFrame_Merged

    def register_single_cell(cell_Data_1, cell_Data_2, input_series):
        """
        Given input series from dataframe cell_Data_1, find the same cell in data frame
        from second round, based on intersection percentage of bounding boxes.

        input_series[0] is the string row index (Cell 1...) of input_series in original dataframe cell_Data_1.
        input_series[1] is the data series in original dataframe cell_Data_1.

        Return False if failed to find the same cell from other round.

        Parameters
        ----------
        input_series : TYPE
            Input series from dataframe cell_Data_1.

        Returns
        -------
        pd_data_of_single_cell : TYPE
            Return False if failed to find the same cell from other round.

        """

        # For each flat cell in round
        bounding_box_str_Data_1 = input_series[1]["BoundingBox_Tag"]
        ImgNameInforString_Data1 = input_series[1]["ImgNameInfor_Tag"]
        # Retrieve boundingbox information
        minr_Data_1 = int(
            bounding_box_str_Data_1[
                bounding_box_str_Data_1.index("minr")
                + 4 : bounding_box_str_Data_1.index("_maxr")
            ]
        )
        maxr_Data_1 = int(
            bounding_box_str_Data_1[
                bounding_box_str_Data_1.index("maxr")
                + 4 : bounding_box_str_Data_1.index("_minc")
            ]
        )
        minc_Data_1 = int(
            bounding_box_str_Data_1[
                bounding_box_str_Data_1.index("minc")
                + 4 : bounding_box_str_Data_1.index("_maxc")
            ]
        )
        maxc_Data_1 = int(
            bounding_box_str_Data_1[
                bounding_box_str_Data_1.index("maxc") + 4 : len(bounding_box_str_Data_1)
            ]
        )

        Area_cell_1 = (maxr_Data_1 - minr_Data_1) * (maxc_Data_1 - minc_Data_1)

        intersection_Area_percentage_list = []
        index_list_Data_2 = []
        # Iterate through DataFrame 2 calculating intersection area
        # Get dataframe of same coordinate in dataframe from next round.
        DataFrame_of_same_coordinate_Data2 = cell_Data_2[
            cell_Data_2["ImgNameInfor_Lib"].str.contains(
                ImgNameInforString_Data1[
                    ImgNameInforString_Data1.index("_R")
                    + 1 : len(ImgNameInforString_Data1)
                ]
            )
        ]

        for index_2, row_Data_2 in DataFrame_of_same_coordinate_Data2.iterrows():
            ImgNameInforString_Data2 = row_Data_2["ImgNameInfor_Lib"]

            bounding_box_str_Data_2 = row_Data_2["BoundingBox_Lib"]
            # Retrieve boundingbox information
            minr_Data_2 = int(
                bounding_box_str_Data_2[
                    bounding_box_str_Data_2.index("minr")
                    + 4 : bounding_box_str_Data_2.index("_maxr")
                ]
            )
            maxr_Data_2 = int(
                bounding_box_str_Data_2[
                    bounding_box_str_Data_2.index("maxr")
                    + 4 : bounding_box_str_Data_2.index("_minc")
                ]
            )
            minc_Data_2 = int(
                bounding_box_str_Data_2[
                    bounding_box_str_Data_2.index("minc")
                    + 4 : bounding_box_str_Data_2.index("_maxc")
                ]
            )
            maxc_Data_2 = int(
                bounding_box_str_Data_2[
                    bounding_box_str_Data_2.index("maxc")
                    + 4 : len(bounding_box_str_Data_2)
                ]
            )

            Area_cell_2 = (maxr_Data_2 - minr_Data_2) * (maxc_Data_2 - minc_Data_2)

            # Overlapping row
            if minr_Data_2 < maxr_Data_1 and maxr_Data_2 > minr_Data_1:
                intersection_rowNumber = min(
                    (abs(minr_Data_2 - maxr_Data_1), maxr_Data_1 - minr_Data_1)
                ) - max(maxr_Data_1 - maxr_Data_2, 0)
            else:
                intersection_rowNumber = 0
            # Overlapping column
            if minc_Data_2 < maxc_Data_1 and maxc_Data_2 > minc_Data_1:
                intersection_colNumber = min(
                    (abs(minc_Data_2 - maxc_Data_1), maxc_Data_1 - minc_Data_1)
                ) - max(maxc_Data_1 - maxc_Data_2, 0)
            else:
                intersection_colNumber = 0

            intersection_Area = intersection_rowNumber * intersection_colNumber
            # Calculate the percentage based on smaller number of intersection over the two.
            intersection_Area_percentage = min(
                [(intersection_Area / Area_cell_1), (intersection_Area / Area_cell_2)]
            )

            intersection_Area_percentage_list.append(intersection_Area_percentage)
            index_list_Data_2.append(index_2)

        if len(intersection_Area_percentage_list) > 0:
            # Link back cells based on intersection area
            if max(intersection_Area_percentage_list) > 0.6:
                # If in DataFrame_2 there's a cell that has a overlapping bounding box, merge and generate a new dataframe.
                Merge_data2_index = index_list_Data_2[
                    intersection_Area_percentage_list.index(
                        max(intersection_Area_percentage_list)
                    )
                ]

                pd_data_of_single_cell = pd.concat(
                    (
                        cell_Data_1.loc[input_series[0]],
                        cell_Data_2.loc[Merge_data2_index],
                    ),
                    axis=0,
                )

                # Add the lib/tag brightness ratio
                Lib_Tag_ratio = pd.DataFrame(
                    [
                        pd_data_of_single_cell.loc["Mean_intensity_in_contour_Lib"]
                        / pd_data_of_single_cell.loc["Mean_intensity_in_contour_Tag"]
                    ],
                    index=["Lib_Tag_contour_ratio"],
                )

                pd_data_of_single_cell = pd.concat(
                    (pd_data_of_single_cell, Lib_Tag_ratio), axis=0
                )
                pd_data_of_single_cell.rename(
                    columns={0: "Cell {}".format(int(input_series[0][5:]))},
                    inplace=True,
                )  # Rename the column name, which is the index name after T.

            else:
                pd_data_of_single_cell = False

        else:
            pd_data_of_single_cell = False

        return pd_data_of_single_cell

    def FilterDataFrames(
        DataFrame,
        Mean_intensity_in_contour_thres,
        Contour_soma_ratio_thres,
        *args,
        **kwargs,
    ):
        """
        Filter the dataframe based on input numbers.

        Parameters
        ----------
        DataFrame : pd.DataFrame.
            Input data.
        Mean_intensity_in_contour_thres : Float.
            Threshold for eliminating dim cells.
        Contour_soma_ratio_thres : Float.
            Threshold for contour soma ratio.

        Returns
        -------
        DataFrames_filtered : pd.DataFrame.
            Filtered dataframe.
        """
        # For lib/tag measurements
        if "Mean_intensity_in_contour_Lib" in DataFrame.columns:
            DataFrames_filtered = DataFrame[
                (
                    DataFrame["Mean_intensity_in_contour_Lib"]
                    > Mean_intensity_in_contour_thres
                )
                & (DataFrame["Contour_soma_ratio_Lib"] > Contour_soma_ratio_thres)
            ]
        # For single round intensity measurements
        elif "Mean_intensity_in_contour" in DataFrame.columns:
            DataFrames_filtered = DataFrame[
                (
                    DataFrame["Mean_intensity_in_contour"]
                    > Mean_intensity_in_contour_thres
                )
                & (DataFrame["Contour_soma_ratio"] > Contour_soma_ratio_thres)
            ]
        # For KC/EC measurements
        elif "Mean_intensity_in_contour_Lib_EC" in DataFrame.columns:
            DataFrames_filtered = DataFrame[
                (
                    DataFrame["Mean_intensity_in_contour_Lib_EC"]
                    > Mean_intensity_in_contour_thres
                )
                & (DataFrame["Contour_soma_ratio_Lib_EC"] > Contour_soma_ratio_thres)
            ]
        # For KC/EC measurements with absolute intensity
        elif "Mean_intensity_in_contour_EC" in DataFrame.columns:
            DataFrames_filtered = DataFrame[
                (
                    DataFrame["Mean_intensity_in_contour_EC"]
                    > Mean_intensity_in_contour_thres
                )
                & (DataFrame["Contour_soma_ratio_EC"] > Contour_soma_ratio_thres)
            ]

        return DataFrames_filtered

    def sort_on_axes(DataFrame, axis_1, axis_2, axis_3, weight_1, weight_2, weight_3):
        """
        Sort the dataframe based on normalized distance calculated from two given axes.

        Parameters
        ----------
        DataFrame : TYPE
            The input dataframe.
        axis_1 : str
            Dataframe column name of the first axis.
        axis_2 : str
            Dataframe column name of the second axis.
        weight_1 : float
            The weight for axis 1 when sorting.
        weight_2 : float
            The weight for axis 2 when sorting.

        Returns
        -------
        DataFrame_sorted : pd.dataframe
            DESCRIPTION.

        """
        # Get the min and max on two axes, prepare for next step.
        Axis_1_min, Axis_1_max = DataFrame[axis_1].min(), DataFrame[axis_1].max()
        Axis_2_min, Axis_2_max = DataFrame[axis_2].min(), DataFrame[axis_2].max()

        if axis_3 == "None":
            DataFrame_sorted = DataFrame.loc[
                (
                    ((DataFrame[axis_1] - Axis_1_min) / (Axis_1_max - Axis_1_min)) ** 2
                    * weight_1
                    + ((DataFrame[axis_2] - Axis_2_min) / (Axis_2_max - Axis_2_min))
                    ** 2
                    * weight_2
                )
                .sort_values(ascending=False)
                .index
            ]
        else:
            Axis_3_min, Axis_3_max = DataFrame[axis_3].min(), DataFrame[axis_3].max()
            DataFrame_sorted = DataFrame.loc[
                (
                    ((DataFrame[axis_1] - Axis_1_min) / (Axis_1_max - Axis_1_min)) ** 2
                    * weight_1
                    + ((DataFrame[axis_2] - Axis_2_min) / (Axis_2_max - Axis_2_min))
                    ** 2
                    * weight_2
                    + ((DataFrame[axis_3] - Axis_3_min) / (Axis_3_max - Axis_3_min))
                    ** 2
                    * weight_3
                )
                .sort_values(ascending=False)
                .index
            ]

        return DataFrame_sorted

    def Convert2Unit8(Imagepath, Rawimage):
        """Convert image pixel values to unit8 to run on MaskRCNN."""
        if Imagepath[len(Imagepath) - 3 : len(Imagepath)] == "tif":
            """set image data type to unit8"""
            image = Rawimage * (255.0 / Rawimage.max())
            image = image.astype(int) + 1

            if len(np.shape(image)) == 2:
                image = gray2rgb(image)

            return image

        else:
            return Rawimage

    #%%
    # =============================================================================
    #     Pixel weighting
    # =============================================================================
    def readbinaryfile(filepath):
        """
        Read in the binary files, which has 'Ip' or 'Vp' as suffix that comes from old Labview code.

        Parameters
        ----------
        filepath : String
            Path to the target numpy file.

        Returns
        -------
        data : np.array
            The inteprated data.
        srate : TYPE
            DESCRIPTION.

        """

        sizebytes = os.path.getsize(filepath)
        inputfilename = filepath

        with open(inputfilename, "rb") as fid:
            data_array_h1 = np.fromfile(fid, count=2, dtype=">d")
            data_array_sc = np.fromfile(
                fid, count=(int(data_array_h1[0]) * int(data_array_h1[1])), dtype=">d"
            )
            data_array_sc = np.reshape(
                data_array_sc, (int(data_array_h1[0]), int(data_array_h1[1])), order="F"
            )

            data_array_h1[1] = 1
            data_array_sc = data_array_sc[:, 1]

            data_array_samplesperchannel = (
                (sizebytes - fid.tell()) / 2 / data_array_h1[1]
            )

            data_array_udat = np.fromfile(
                fid,
                count=(int(data_array_h1[1]) * int(data_array_samplesperchannel)),
                dtype=">H",
            )  # read as uint16
            data_array_udat_1 = data_array_udat.astype(
                np.int32
            )  # convertdtype here as data might be saturated, out of uint16 range
            data_array_sdat = data_array_udat_1 - (2 ** 15)

        temp = np.ones(int(data_array_samplesperchannel)) * data_array_sc[1]

        for i in range(1, int(data_array_h1[0]) - 1):
            L = (
                np.ones(int(data_array_samplesperchannel)) * data_array_sc[i + 1]
            ) * np.power(data_array_sdat, i)
            temp = temp + L

        data = temp
        srate = data_array_sc[0]

        return data, srate

    def extractV(video, Vin):
        """
        Perform the correlation between input video and voltage signal or trace of video itself,
        calculate the weighted pixel information.

        Parameters
        ----------
        video : np.array
            The input video in numpy array format.
        Vin : np.array
            Input patch voltage signals or camera trace, with which the video correlate.

        Returns
        -------
        corrimage : np.array
            DF/DV image.
        weightimage : np.array
            1/sigmaimage, in units of 1/voltage^2.
        sigmaimage : np.array
            The variance between predicted "voltage" and input voltage.

        """
        readin_video = video.copy()
        readin_voltage_patch = Vin.copy()

        sizex = readin_video.shape[1]
        sizey = readin_video.shape[2]

        # This is the mean intensity image of the whole video stack.
        video_mean_image = np.mean(readin_video, axis=0)

        # Mean value of the waveform that you want to correlate with(patch clamp voltage signal or camera trace).
        average_voltage = np.mean(readin_voltage_patch)

        # 1-D array of variance of voltage signal.
        readin_voltage_variance = readin_voltage_patch - average_voltage
        voltagelength = len(readin_voltage_patch)

        # ----------------------Subtract off background-------------------------
        # Reshape the mean intensity 2D image to 3D, to the same length as voltage signal.
        averageimage_tiled = np.tile(video_mean_image, (voltagelength, 1, 1))

        # 3-D array of variance between each frame from raw video and the total mean intensity image.
        readin_video_variance = readin_video - averageimage_tiled

        # -----Correlate the changes in intensity with the applied voltage------
        # Reshape the 1D readin_voltage_variance into 3D.
        readin_voltage_variance_3D = np.resize(
            readin_voltage_variance, (voltagelength, 1, 1)
        )

        readin_video_variance_copy = readin_video_variance.copy()

        # At each frame, get the product of video_variance and voltage_variance
        #  = DV*DF
        for i in range(voltagelength):
            readin_video_variance_copy[i] = (
                readin_video_variance_copy[i] * readin_voltage_variance_3D[i]
            )

        # Normalize to magnitude of voltage changes (DV*DF./DV^2) = DF/DV
        corrimage = np.mean(readin_video_variance_copy, axis=0) / np.mean(
            ((readin_voltage_variance) ** 2)
        )

        # Calculate a dV estimate at each pixel, based on the linear regression.
        corrmat = np.tile(corrimage, (voltagelength, 1, 1))

        # At each pixel in video, get predicted DV
        # DF/(DF/DV) = DV
        estimate_DV = readin_video_variance / corrmat

        imtermediate = np.zeros(estimate_DV.shape)

        # --------Look at the residuals to get a noise at each pixel-----------
        for i in range(voltagelength):
            # At each frame, compute the variance between predicted "voltage" and input voltage.
            imtermediate[i] = (estimate_DV[i] - readin_voltage_variance_3D[i]) ** 2
        sigmaimage = np.mean(imtermediate, axis=0)  # 2D

        # Weightimg scales inverted with variance between input voltage and measured "voltage";
        # Variance is expressed in units of voltage squared. standard way to do it would be to cast input voltage in form of fit and leave data as data.
        weightimage = 1 / sigmaimage  # 1/v**2

        weightimage[np.isnan(weightimage)] = 0
        # Normalize it, so that there's no unit.
        # At each pixel position, generate a percentage weight of this pixel, e.g., 0 for background pixels.
        weightimage = weightimage / np.mean(weightimage)

        estimate_DV[np.isnan(estimate_DV)] = 0  # Set places where imgs2 == NaN to zero
        """
        dVout = squeeze(mean(mean(imgs2.*repmat(weightimg, [1 1 L])))) #squeeze takes something along the time axis and puts it 1xn vector

        Vout = dVout + avgV
        offsetimg = avgimg - avgV*corrimg
        """

        return corrimage, weightimage, sigmaimage

    #%%
    # =============================================================================
    #     1-D array processing
    # =============================================================================
    def signal_to_noise(a, axis=0, ddof=0):
        """
        The signal-to-noise ratio of the input data.
        Returns the signal-to-noise ratio of `a`, here defined as the mean
        divided by the standard deviation.
        Parameters
        ----------
        a : array_like
            An array_like object containing the sample data.
        axis : int or None, optional
            If axis is equal to None, the array is first ravel'd. If axis is an
            integer, this is the axis over which to operate. Default is 0.
        ddof : int, optional
            Degrees of freedom correction for standard deviation. Default is 0.
        Returns
        -------
        s2n : ndarray
            The mean to standard deviation ratio(s) along `axis`, or 0 where the
            standard deviation is 0.
        """
        a = np.asanyarray(a)
        m = a.mean(axis)
        sd = a.std(axis=axis, ddof=ddof)
        return np.where(sd == 0, 0, m / sd)

    def frequency_analysis(array, show_result=True):
        """
        Return the fft frequency analysis of input array.

        Parameters
        ----------
        array : array_like
            An array_like object containing the sample data.
        show_result : bool, optional
            If show the results. The default is True.

        Returns
        -------
        freqs : array_like
            frequency amplitude array.

        """

        FFT = abs(scipy.fft.fft(array))
        freqs = fftpack.fftfreq(len(array)) * 5000

        if show_result == True:
            pylab.subplot(211)
            pylab.plot(
                array[
                    2:,
                ]
            )
            pylab.subplot(212)
            pylab.plot(freqs, 20 * scipy.log10(FFT), "x")
            pylab.xlim(1, 500)
            pylab.show()

        return freqs

    def gaussian_fit(raw_data_list, interpolate_factor=10):
        """
        Return the gaussian fit of input number list.
        X axis is interpolated 10 times by default.

        Parameters
        ----------
        raw_data_list : list
            input number list.

        Returns
        -------
        fitted_curve : np.array
            Gaussian fit of input number list.

        """
        focus_degree_array = np.asarray(raw_data_list)

        x_axis = np.arange(len(raw_data_list))

        n = len(raw_data_list)  # the number of data
        mean = sum(x_axis * focus_degree_array) / n  # mean value of data
        sigma = (
            sum(focus_degree_array * (x_axis - mean) ** 2) / n
        )  # note this correction

        def gaus(x, a, x0, sigma):
            return a * np.exp(-((x - x0) ** 2) / (2 * sigma ** 2))

        popt, pcov = curve_fit(gaus, x_axis, focus_degree_array)

        # Generate the inpterpolated new x axis.
        x_axis_new = np.linspace(0, x_axis[-1], len(x_axis) * interpolate_factor)

        fitted_curve = gaus(x_axis_new, *popt)

        return fitted_curve

    def interpolate_1D(input_array, desired_number=None):
        """
        interpolate_1D

        Parameters
        ----------
        input_array : np.array
            DESCRIPTION.
        desired_number : int, optional
            Number of elements in final array. The default is None.

        Returns
        -------
        interpolated : np.array
            DESCRIPTION.

        """
        f = interpolate.interp1d(np.arange(len(input_array)), input_array)

        if desired_number == None:
            xnew = np.linspace(
                0, np.amax(np.arange(len(input_array))), len(input_array) * 10
            )
        else:
            xnew = np.linspace(0, np.amax(np.arange(len(input_array))), desired_number)

        interpolated = f(xnew)

        return interpolated
    
    def threshold_seperator(array, threshold):
        """
        Given a array and a threshold, devide the array into above and below parts,
        return the index range for both.

        Parameters
        ----------
        array : np.array
            DESCRIPTION.
        threshold : float
            Threshold for deviding.

        Returns
        -------
        upper_index_dict : dict
            DESCRIPTION.
        lower_index_dict : dict
            DESCRIPTION.

        """
        upper_index_dict = {}
        lower_index_dict = {}
        
        for i in range(2):
        # Each loop for either upper or lower part
            if i == 0:
                qualified_index_array = np.where(array >= threshold)[0]
            else:
                qualified_index_array = np.where(array < threshold)[0]
            
            # Generate the discontinue index list
            discontinue_index_list = []
            for qualified_index in range(len(qualified_index_array)):
                if qualified_index > 0:
                    # Find the disconnect point
                    if qualified_index_array[qualified_index] - qualified_index_array[qualified_index-1] > 1:
                        discontinue_index_list.append(qualified_index)
                        
            phase_index = 0
            
            for index in range(len(discontinue_index_list) + 1):
                if phase_index == 0:
                # For the first phase detected
                    start_index = 0
                    start_index_of_next_phase = discontinue_index_list[0] -1
                    
                elif phase_index < len(discontinue_index_list):
                # For the middle ones
                    start_index = discontinue_index_list[index - 1]
                    start_index_of_next_phase = discontinue_index_list[index] -1
                    
                elif phase_index == len(discontinue_index_list):
                # For the end of the phase
                    start_index = discontinue_index_list[index - 1]
                    start_index_of_next_phase = len(qualified_index_array) -1
            
                if i == 0:
                # For the upper part
                    upper_index_dict["phase {}".format(str(phase_index))] = [qualified_index_array[start_index], qualified_index_array[start_index_of_next_phase] + 1]

                else:
                # For the lower part
                    lower_index_dict["phase {}".format(str(phase_index))] = [qualified_index_array[start_index], qualified_index_array[start_index_of_next_phase] + 1]
                    
                phase_index += 1                    
                
        return upper_index_dict, lower_index_dict
                        
            
    #%%
    # =============================================================================
    #     2-D array processing
    # =============================================================================
    def variance_of_laplacian(image):
        """
        Compute the Laplacian of the image and then return the focus
        measure, which is simply the variance of the Laplacian

        Parameters
        ----------
        image : np.array
            Gray scale input image.

        Returns
        -------
        sharpness : float
            Sharpness of the image, the higher the better.

        """
        # if image.shape[2] == 3:
        #     image = rgb2gray(image)

        # Blur the image a bit.
        image = cv2.GaussianBlur(image, (3, 3), 0)

        # convolution of 3 x 3 kernel, according to different datatype.
        if type(image[0, 0]) == np.float32:
            sharpness = cv2.Laplacian(image, cv2.CV_32F).var()
        elif type(image[0, 0]) == np.float64:
            sharpness = cv2.Laplacian(image, cv2.CV_64F).var()
        elif type(image[0, 0]) == np.float64:
            sharpness = cv2.Laplacian(image, cv2.CV_64F).var()
        elif type(image[0, 0]) == np.uint8:
            sharpness = cv2.Laplacian(image, cv2.CV_8U).var()
        elif type(image[0, 0]) == np.uint16:
            sharpness = cv2.Laplacian(image, cv2.CV_16U).var()

        return sharpness

    def local_entropy(image, amax=3, disk_size=20):
        """
        Calculate the local entropy of input image.

        Parameters
        ----------
        image : TYPE
            DESCRIPTION.
        amax : float, optional
            Ceiling value for normalization. The default is 3.
            If set to None, the ceiling will be the maximum.
        disk_size : int, optional
            Disk size when calculating entropy. The default is 20.

        Returns
        -------
        TYPE
            DESCRIPTION.

        """
        if amax == None:
            image_uint8 = img_as_ubyte(image / np.amax(image))
        else:
            image = np.where(image >= amax, amax, image)
            image_uint8 = img_as_ubyte(image / amax)
        entropy_image = entropy(image_uint8, disk(disk_size))

        return np.mean(entropy_image)

    def images_difference(imageA, imageB):
        # the 'Mean Squared Error' between the two images is the
        # sum of the squared difference between the two images;
        # NOTE: the two images must have the same dimension
        imageA_unit8 = imageA * (255.0 / imageA.max())
        imageA_unit8 = imageA_unit8.astype(int) + 1

        imageB_unit8 = imageB * (255.0 / imageB.max())
        imageB_unit8 = imageB_unit8.astype(int) + 1

        err = np.sum((imageA_unit8 - imageB_unit8) ** 2)
        err /= float(imageA.shape[0] * imageA.shape[1])

        # return the MSE, the lower the error, the more "similar"
        # the two images are
        return err

    def illumination_correction(laser_profile, camera_base_values=100):

        # The base value is the pixel value for camera sensor under no light, for Hamamastu it's normally 100.
        camera_base_image = (
            np.ones((laser_profile.shape[0], laser_profile.shape[1])).astype(np.uint16)
            * camera_base_values
        )

        laser_profile_without_baseline = np.abs(
            (laser_profile - camera_base_image)
            * ((laser_profile - camera_base_image) > 0)
        )

        return laser_profile_without_baseline

    def image_stack_calculation(image_file_names, operation="mean"):
        """
        Given a list of image file names, operate and output an image from it.

        Parameters
        ----------
        image_file_names : list
            List of image file names.
        operation : string, optional
            Type of operation. The default is "mean".

            -- mean: calculate the average of images stack.
            -- max projection: calculate the max projection over the stack.

        Returns
        -------
        output : TYPE
            DESCRIPTION.

        """
        image_index = 0
        for image_file_name in image_file_names:
            single_image = imread(image_file_name)

            # stack the images
            if image_index == 0:
                image_stack = single_image[np.newaxis, :, :]
            else:
                image_stack = np.concatenate(
                    (image_stack, single_image[np.newaxis, :, :]), axis=0
                )

        if operation == "mean":
            output = np.mean(image_stack, axis=0)
        elif operation == "max projection":
            output = np.max(image_stack, axis=0)

        return output

    #%%
    # =============================================================================
    #     Screening data post-processing
    # =============================================================================
    def find_repeat_imgs(Nest_data_directory, similarity_thres=0.04):
        """
        Find repeating images inside diretory.

        Parameters
        ----------
        Nest_data_directory : str
            DESCRIPTION.
        similarity_thres : float, optional
            DESCRIPTION. The default is 0.04.

        Returns
        -------
        similar_img_list : TYPE
            DESCRIPTION.
        img_diff_list : TYPE
            DESCRIPTION.

        """
        (
            RoundNumberList,
            CoordinatesList,
            fileNameList,
        ) = ProcessImage.retrive_scanning_scheme(
            Nest_data_directory, row_data_folder=True
        )

        similar_img_list = []
        img_diff_list = []
        for Round in RoundNumberList:
            fileNameList_oneRound = []
            for fileName in fileNameList:
                if fileName.startswith(Round):
                    # Generate name list only from one round
                    fileNameList_oneRound.append(fileName)

            for fileIndex_oneRound in range(len(fileNameList_oneRound)):
                # If not the last image:
                if fileIndex_oneRound != len(fileNameList_oneRound) - 1:
                    fileName_oneRound = fileNameList_oneRound[fileIndex_oneRound]
                    previous_image = imread(
                        os.path.join(Nest_data_directory, fileName_oneRound)
                    )
                    # Assume that file names are in sequence.
                    next_image = imread(
                        os.path.join(
                            Nest_data_directory,
                            fileNameList_oneRound[fileIndex_oneRound + 1],
                        )
                    )

                    img_diff = ProcessImage.images_difference(
                        previous_image, next_image
                    )
                    img_diff_list.append(img_diff)
                    if img_diff < similarity_thres:
                        similar_img_list.append(
                            fileNameList_oneRound[fileIndex_oneRound + 1]
                        )

        return similar_img_list, img_diff_list

    def find_infocus_from_stack(Nest_data_directory, save_image=True):
        """
        Given the directory, walk through all the images with 'Zmax' in its name
        and find the image with highest focus degree.

        Parameters
        ----------
        Nest_data_directory : TYPE
            DESCRIPTION.
        save_image : TYPE, optional
            DESCRIPTION. The default is True.

        Returns
        -------
        None.

        """
        (
            RoundNumberList,
            CoordinatesList,
            fileNameList,
        ) = ProcessImage.retrive_scanning_scheme(Nest_data_directory)

        for each_file_name in fileNameList:
            # For each coordinate, find all position files in the stack, according to Zmax file name.
            file_name_stack = []
            for file in os.listdir(Nest_data_directory):
                if each_file_name[0 : each_file_name.index("Zmax")] + "Zpos" in file:
                    file_name_stack.append(file)

            img_stack = []
            for file in file_name_stack:
                img_stack.append(imread(os.path.join(Nest_data_directory, file)))

            img_with_highest_focus_degree = ProcessImage.find_infocus_from_list(
                img_stack
            )
            if save_image == True:
                # Save the file.
                with skimtiff.TiffWriter(
                    os.path.join(
                        Nest_data_directory,
                        each_file_name[0 : each_file_name.index("max")] + "focus.tif",
                    ),
                    imagej=True,
                ) as tif:
                    tif.save(
                        img_with_highest_focus_degree.astype("float32"), compress=0
                    )

    def find_infocus_from_list(img_stack):
        """
        Find the most in-focus image from the image list.

        Parameters
        ----------
        img_stack : list
            List of input images.

        Returns
        -------
        img_highest_focus_degree : np.ndarray
            Best in-focus image.

        """
        focus_degree_list = []
        for each_img in img_stack:
            focus_degree_list.append(ProcessImage.local_entropy(each_img))

        img_highest_focus_degree = img_stack[
            focus_degree_list.index(max(focus_degree_list))
        ]

        return img_highest_focus_degree

    def cam_screening_post_processing(directory, save_max_projection=True):

        (
            RoundNumberList,
            CoordinatesList,
            fileNameList,
        ) = ProcessImage.retrive_scanning_scheme(directory, file_keyword="Cam")

        for each_round in RoundNumberList:
            # Do Z-stack max projection
            for each_coordinate in CoordinatesList:

                # list of z stack images of same coordinate.
                img_zstack_list = []
                for each_file_name in fileNameList:
                    if each_coordinate in each_file_name:
                        img_zstack_list.append(each_file_name)

                # ---------------------------------------------Calculate the z max projection-----------------------------------------------------------------------
                ZStackOrder = 0
                for each_z_img_filename in img_zstack_list:
                    each_z_img = imread(os.path.join(directory, each_z_img_filename))
                    if ZStackOrder == 0:
                        Cam_image_maxprojection_stack = each_z_img[np.newaxis, :, :]
                    else:
                        Cam_image_maxprojection_stack = np.concatenate(
                            (
                                Cam_image_maxprojection_stack,
                                each_z_img[np.newaxis, :, :],
                            ),
                            axis=0,
                        )
                    ZStackOrder += 1

                # Save the max projection image
                if ZStackOrder == len(img_zstack_list):
                    Cam_image_maxprojection = np.max(
                        Cam_image_maxprojection_stack, axis=0
                    )

                    if not os.path.exists(os.path.join(directory, "maxProjection")):
                        # If the folder is not there, create the folder
                        os.mkdir(os.path.join(directory, "maxProjection"))
                    if save_max_projection == True:
                        # Save the zmax file.
                        with skimtiff.TiffWriter(
                            os.path.join(
                                directory,
                                "maxProjection\\"
                                + each_round
                                + "_"
                                + each_coordinate
                                + "_Cam_"
                                + "Zmax"
                                + ".tif",
                            ),
                            imagej=True,
                        ) as tif:
                            tif.save(
                                Cam_image_maxprojection.astype("int16"), compress=0
                            )

        # return img_zstack_list

    #%%
    # =============================================================================
    #     Images stitching
    # =============================================================================
    def image_stitching(Nest_data_directory, row_data_folder=True):
        """
        Stitch all screening images together into one.

        Parameters
        ----------
        Nest_data_directory : string
            Directory in which all images are stored.
        row_data_folder : bool, optional
            For MaskRCNN stitching, this is False. The default is True.

        Returns
        -------
        Stitched_image_dict : dict
            Dict containing stitched images of all rounds.

        """
        (
            RoundNumberList,
            CoordinatesList,
            fileNameList,
        ) = ProcessImage.retrive_scanning_scheme(Nest_data_directory, row_data_folder)

        imageinfo_DataFrame = []
        for Each_round in RoundNumberList:
            for Each_coord_image_filename in fileNameList:
                if (
                    Each_round in Each_coord_image_filename
                ):  # Loop through each image in round

                    if row_data_folder == True:
                        Coord_text = Each_coord_image_filename[
                            Each_coord_image_filename.index(
                                "_R"
                            ) : Each_coord_image_filename.index("_PMT")
                        ]
                    else:
                        Coord_text = Each_coord_image_filename[
                            Each_coord_image_filename.index("_R") : len(
                                Each_coord_image_filename
                            )
                            - 4
                        ]

                    Stage_row_index = int(Coord_text[2 : Coord_text.index("C")])
                    Stage_column_index = int(
                        Coord_text[Coord_text.index("C") + 1 : len(Coord_text)]
                    )
                    imageinfo_DataFrame.append(
                        dict(
                            zip(
                                [
                                    "Round",
                                    "File name",
                                    "Stage row index",
                                    "Stage column index",
                                ],
                                [
                                    Each_round,
                                    Each_coord_image_filename,
                                    Stage_row_index,
                                    Stage_column_index,
                                ],
                            )
                        )
                    )
        # Generate the data frame which contains coordinates information
        imageinfo_DataFrame = pd.DataFrame(imageinfo_DataFrame)

        # Get the scanning step size
        if (
            imageinfo_DataFrame.iloc[0]["Stage row index"]
            != imageinfo_DataFrame.iloc[1]["Stage row index"]
        ):
            scanning_coord_step = (
                imageinfo_DataFrame.iloc[1]["Stage row index"]
                - imageinfo_DataFrame.iloc[0]["Stage row index"]
            )
        else:
            scanning_coord_step = (
                imageinfo_DataFrame.iloc[1]["Stage column index"]
                - imageinfo_DataFrame.iloc[0]["Stage column index"]
            )

        scanning_coord_step = 1585
        print("scanning_coord_step set to {}!".format(scanning_coord_step))

        # Assume that col and row coordinates numbers are the same.
        max_coord_value = imageinfo_DataFrame["Stage column index"].max()
        number_of_coord = int(max_coord_value / scanning_coord_step + 1)

        # Get the pixel number of image.
        example_image = imread(os.path.join(Nest_data_directory, fileNameList[0]))
        if row_data_folder == True:
            image_pixel_number = example_image.shape[0]
        else:  # In ML masks there's a white line at the bottom of image.
            image_pixel_number = example_image.shape[0] - 1

        Stitched_image_dict = {}
        for Each_round in RoundNumberList:
            # Create the empty array holder
            final_image_size = image_pixel_number * number_of_coord
            if row_data_folder == True:
                final_image_holder = np.empty((final_image_size, final_image_size))
            else:
                # For ML mask assembly, its RGBA format, size MxNx4.
                final_image_holder = np.empty(
                    (final_image_size, final_image_size, 4), dtype="uint8"
                )

            for index, row_Data in imageinfo_DataFrame.iterrows():
                if Each_round == row_Data["Round"]:
                    # col and row in stage coordinates are opposite of np coordinates

                    final_image_holder_col_start = (
                        final_image_size
                        - image_pixel_number
                        * (int(row_Data["Stage row index"] / scanning_coord_step) + 1)
                    )
                    final_image_holder_row_start = image_pixel_number * (
                        int(row_Data["Stage column index"] / scanning_coord_step)
                    )

                    row_image = imread(
                        os.path.join(Nest_data_directory, row_Data["File name"])
                    )

                    if row_data_folder == True:
                        final_image_holder[
                            final_image_holder_row_start : final_image_holder_row_start
                            + image_pixel_number,
                            final_image_holder_col_start : final_image_holder_col_start
                            + image_pixel_number,
                        ] = row_image
                    else:  # In ML masks there's a white line at the bottom of image, needs to crop it.
                        final_image_holder[
                            final_image_holder_row_start : final_image_holder_row_start
                            + image_pixel_number,
                            final_image_holder_col_start : final_image_holder_col_start
                            + image_pixel_number,
                        ] = row_image[0:image_pixel_number, 0:image_pixel_number, :]

            Stitched_image_dict[Each_round] = final_image_holder

        return Stitched_image_dict

    def retrieve_focus_map(Nest_data_directory):
        """
        Retrieve the objective motor position from images meta data, and map it.

        Parameters
        ----------
        Nest_data_directory : string
             Directory in which all images are stored.

        Returns
        -------
        focus_map_dict : dict
            Dict containing focus position of recorded images of all rounds.

        """
        (
            RoundNumberList,
            CoordinatesList,
            fileNameList,
        ) = ProcessImage.retrive_scanning_scheme(Nest_data_directory)

        imageinfo_DataFrame = []
        for Each_round in RoundNumberList:
            for Each_coord_image_filename in fileNameList:
                if (
                    Each_round in Each_coord_image_filename
                ):  # Loop through each image in round

                    Coord_text = Each_coord_image_filename[
                        Each_coord_image_filename.index(
                            "_R"
                        ) : Each_coord_image_filename.index("_PMT")
                    ]
                    Stage_row_index = int(Coord_text[2 : Coord_text.index("C")])
                    Stage_column_index = int(
                        Coord_text[Coord_text.index("C") + 1 : len(Coord_text)]
                    )
                    imageinfo_DataFrame.append(
                        dict(
                            zip(
                                [
                                    "Round",
                                    "File name",
                                    "Stage row index",
                                    "Stage column index",
                                ],
                                [
                                    Each_round,
                                    Each_coord_image_filename,
                                    Stage_row_index,
                                    Stage_column_index,
                                ],
                            )
                        )
                    )
        # Generate the data frame which contains coordinates information
        imageinfo_DataFrame = pd.DataFrame(imageinfo_DataFrame)

        # Get the scanning step size
        if (
            imageinfo_DataFrame.iloc[0]["Stage row index"]
            != imageinfo_DataFrame.iloc[1]["Stage row index"]
        ):
            scanning_coord_step = (
                imageinfo_DataFrame.iloc[1]["Stage row index"]
                - imageinfo_DataFrame.iloc[0]["Stage row index"]
            )
        else:
            scanning_coord_step = (
                imageinfo_DataFrame.iloc[1]["Stage column index"]
                - imageinfo_DataFrame.iloc[0]["Stage column index"]
            )

        # Assume that col and row coordinates numbers are the same.
        max_coord_value = imageinfo_DataFrame["Stage column index"].max()
        number_of_coord = int(max_coord_value / scanning_coord_step + 1)

        focus_map_dict = {}
        for Each_round in RoundNumberList:
            # Create the empty array holder
            final_focus_map_holder = np.empty((number_of_coord, number_of_coord))

            for index, row_Data in imageinfo_DataFrame.iterrows():
                if Each_round == row_Data["Round"]:
                    # col and row in stage coordinates are opposite of np coordinates

                    final_focus_map_col_start = number_of_coord - (
                        int(row_Data["Stage row index"] / scanning_coord_step) + 1
                    )
                    final_focus_map_row_start = int(
                        row_Data["Stage column index"] / scanning_coord_step
                    )

                    # Read the metadata and extract the focus position information.
                    with Image.open(
                        os.path.join(Nest_data_directory, row_Data["File name"])
                    ) as img:
                        meta_dict = {TAGS[key]: img.tag[key] for key in img.tag.keys()}
                        ImageDescription = meta_dict["ImageDescription"][0]
                        objective_position = float(
                            ImageDescription[
                                ImageDescription.index("focuspos: =")
                                + 11 : len(ImageDescription)
                                - 1
                            ]
                        )

                    final_focus_map_holder[
                        final_focus_map_row_start : final_focus_map_row_start + 1,
                        final_focus_map_col_start : final_focus_map_col_start + 1,
                    ] = objective_position

            focus_map_dict[Each_round] = final_focus_map_holder

        return focus_map_dict
    
    #%%
    # =============================================================================
    #     For photo current calculation
    # =============================================================================

    def PhotoCurrent(
        main_directory,
        marker = "blankingall",
        rhodopsin="Not specified",
    ):  
        
        main_directory = main_directory

        for file in os.listdir(main_directory):
            if "Wavefroms_sr_" in file and "npy" in file:
                wave_fileName = os.path.join(main_directory, file)
                temp_wave_container = np.load(wave_fileName, allow_pickle=True)
            if "Ip" in file and "npy" in file:
                current_fileName = os.path.join(main_directory, file)
                temp_current_container = np.load(current_fileName, allow_pickle=True)
                # Here in raw file, first 5 numbers are meta data, then in the beginning
                # and the end both have a 0 extra recording to reset the NIDAQ channel.
                current_curve = temp_current_container[6:len(temp_current_container)-1]
                
                plt.figure()
                plt.plot(current_curve)
                plt.show()
        # Get the blanking waveform as indication of laser on and off.
        for i in temp_wave_container:
            if i['Sepcification'] == marker:
                blanking_waveform = i['Waveform'][1:len(i['Waveform'])-1]

        laser_on_phases, laser_off_phases= ProcessImage.threshold_seperator(blanking_waveform, 1)
        print(laser_on_phases)
        
        for phase_key in laser_on_phases:
            
            current_each_phase = current_curve[laser_on_phases[phase_key][0] : laser_on_phases[phase_key][1]]
            plt.figure()
            plt.plot(current_each_phase)
            plt.show()
            
            print("Mean value of each phase: {}".format(np.mean(current_each_phase)))

    #%%
    # =============================================================================
    #     Curve fitting, adapted from Mels' code.
    # =============================================================================


class CurveFit:
    def __init__(
        self,
        fluorescence,
        waveform,
        camera_fps,
        DAQ_sampling_rate,
        skip=3,
        main_directory=None,
        rhodopsin="Not specified",
    ):

        #### Input for initialization of the class ####
        # fluorescence   = Weighted trace of fluorescence signal
        # waveform       = waveform generated with Native Instruments DAQ
        # rhodopsin      = label for the data (e.g., 'Helios4')
        # Total_time     = Total recording time of camera
        # camera_fps     = Frames per second of the recording camera
        # V_Hz           = Frequency of the periodic voltage waveform
        # DAQ_sampling_rate         = Sampling frequency of provided voltage waveform
        # skip           = Skip(number of periods in the beginning) to period where rhodopsin has reach steady state fluorescence
        self.camera_fps = camera_fps
        self.DAQ_sampling_rate = DAQ_sampling_rate
        self.skip = int(skip)
        self.fluorescence = fluorescence
        self.time = (
            (np.arange(len(self.fluorescence)) + 1) * 1 / self.camera_fps
        )  # Time axis for camera fluorescence signal
        self.rhodopsin = rhodopsin
        self.waveform = waveform[
            7:
        ]  # First 5 elements are meta data. Last or first 2 can be neglected
        self.total_time = round(len(self.waveform) / DAQ_sampling_rate)
        self.waveformcopy = self.waveform.copy()
        self.timewaveform = (
            (np.arange(len(self.waveform)) + 1) * 1 / self.DAQ_sampling_rate
        )  # Time axis for waveform signal
        self.main_directory = main_directory

    def Photobleach(self):

        # Bi-exponential curve for the fitting algorithm
        def bleachfunc(t, a, t1, b, t2):
            return a * np.exp(-(t / t1)) + b * np.exp(-(t / t2))

        # Parameter bounds for the parameters in the bi-exponential function
        parameter_bounds = ([0, 0, 0, 0], [np.inf, np.inf, np.inf, np.inf])

        # popt   = Optimal parameters for the curve fit
        # pcov   = The estimated covariance of popt
        popt, pcov = curve_fit(
            bleachfunc,
            self.time,
            self.fluorescence,
            bounds=parameter_bounds,
            maxfev=500000,
        )

        # Vizualization before photobleach normalization
        fig1, ax = plt.subplots(figsize=(8.0, 5.8))
        (p01,) = ax.plot(
            self.time,
            self.fluorescence,
            color=(0, 0, 0.4),
            linestyle="None",
            marker="o",
            markersize=0.5,
            markerfacecolor=(0, 0, 0.9),
            label="Experimental data",
        )
        (p02,) = ax.plot(
            self.time,
            bleachfunc(self.time, *popt),
            color=(0.9, 0, 0),
            label="Bi-exponential fit",
        )
        ax.set_title(self.rhodopsin, size=14)
        ax.set_ylabel("Fluorescence (counts)", fontsize=11)
        ax.set_xlabel("Time (s)", fontsize=11)
        ax.legend([p02, p01], ["Bi-exponential fit", "Experimental data"])
        ax.spines["right"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax.xaxis.set_ticks_position("bottom")
        ax.yaxis.set_ticks_position("left")
        plt.show()
        if self.main_directory != None:
            fig1.savefig(
                (
                    os.path.join(
                        self.main_directory,
                        "Analysis results//Fluorescence trace with fitting.png",
                    )
                ),
                dpi=1000,
            )

        # Normalization of fluorescence signal (e.g., division by the fit)
        self.fluorescence_trace_for_sensitivity = np.true_divide(
            self.fluorescence, bleachfunc(self.time, *popt)
        )

        # Here substract the fitted base line in order to calculate time constants.
        self.fluorescence_for_kinetics = self.fluorescence - bleachfunc(
            self.time, *popt
        )

        # Vizualization after photobleach normalization
        fig2, ax = plt.subplots(figsize=(8.0, 5.8))
        (p03,) = ax.plot(self.time, self.fluorescence_trace_for_sensitivity)
        ax.set_title("Bleach normalized fluorescence trace", size=14)
        ax.set_ylabel("Fluorescence (a.u.)", fontsize=11)
        ax.set_xlabel("Time (s)", fontsize=11)
        ax.spines["right"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax.xaxis.set_ticks_position("bottom")
        ax.yaxis.set_ticks_position("left")
        plt.show()
        if self.main_directory != None:
            fig2.savefig(
                (
                    os.path.join(
                        self.main_directory,
                        "Analysis results//Bleach normalized fluorescence trace.png",
                    )
                ),
                dpi=1000,
            )

        fig3, ax = plt.subplots(figsize=(8.0, 5.8))
        (p04,) = ax.plot(self.time, self.fluorescence_for_kinetics)
        ax.set_title("Bleach substracted fluorescence trace", size=14)
        ax.set_ylabel("Fluorescence (counts)", fontsize=11)
        ax.set_xlabel("Time (s)", fontsize=11)
        ax.spines["right"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax.xaxis.set_ticks_position("bottom")
        ax.yaxis.set_ticks_position("left")
        plt.show()
        if self.main_directory != None:
            fig3.savefig(
                (
                    os.path.join(
                        self.main_directory,
                        "Analysis results//Bleach substracted fluorescence trace.png",
                    )
                ),
                dpi=1000,
            )

        # Vizualization of waveform provided
        # fig3, ax = plt.subplots()
        # p04, = ax.plot(self.timewaveform, self.waveform*1000/10) # *1000 is to convert to mV; 10 is to correct for the *10 gain at the patch clamp amplifier.
        # ax.set_title('Voltage waveform', size=14)
        # ax.set_ylabel('Voltage (mV)', fontsize=11)
        # ax.set_xlabel('Time (s)', fontsize=11)
        # ax.spines['right'].set_visible(False)
        # ax.spines['top'].set_visible(False)
        # ax.xaxis.set_ticks_position('bottom')
        # ax.yaxis.set_ticks_position('left')
        # plt.show()
        # Uncomment if you want to save the figure
        # plt.savefig()

        # Store parameters for the photobleach bi-exponential fit
        # The conditionals make sure that 't1' is always the fast
        # time component and 't2' is the slow time component
        if popt[1] < popt[3]:
            self.photobleach_a = popt[0]
            self.photobleach_t1 = popt[1]
            self.photobleach_b = popt[2]
            self.photobleach_t2 = popt[3]
            self.photobleach_ratio1 = popt[0] / (popt[0] + popt[2])
            self.photobleach_ratio2 = 1 - self.photobleach_ratio1
        else:
            self.photobleach_a = popt[2]
            self.photobleach_t1 = popt[3]
            self.photobleach_b = popt[0]
            self.photobleach_t2 = popt[1]
            self.photobleach_ratio1 = popt[2] / (popt[0] + popt[2])
            self.photobleach_ratio2 = 1 - self.photobleach_ratio1

        return self.photobleach_t1, self.photobleach_t2, self.photobleach_ratio1

    def IsolatePeriods(self):

        # Initialize empty periodic fluorescence and periodic time list
        self.periods_fluorescence_sensitivity = []
        self.periods_fluorescence_kinetics = []
        self.periods_time = []

        # Find the midpoint of a step provided in the waveform
        self.midpoint = (np.amax(self.waveform) + np.amin(self.waveform)) / 2

        # True values        = values belonging top of square wave
        # False values       = values belonging to bottom of square wave
        self.waveform = self.waveform > self.midpoint
        self.waveform[
            :2
        ] = True  # This line is redundant if you skip the first 7 values of the waveform
        self.waveform_time_matrix = np.column_stack((self.waveform, self.timewaveform))

        # Find indices where steps happen
        self.step_idx = (
            np.argwhere(np.diff(self.waveform_time_matrix[:, 0]) != 0).reshape(-1) + 1
        )

        ##### Initialize empty lists needed for the next for loop ####
        # fluorescence_list_true     = list for fluorescence signal belonging to top of square wave
        # fluorescence_list_false    = list for fluorescence signal belonging to bottom of square wave
        # time_list_true             = list for time points belonging to top of square wave
        # time_list_false            = list for time points belonging to bottom of square wave
        # time_difference            = list for trigger time difference (difference between time point of fluorescence signal
        #                             and voltage waveform directly after each step)
        # counter                    =
        self.fluorescence_list_true = []
        self.fluorescence_list_false = []
        self.fluorescence_list_true_1 = []
        self.fluorescence_list_false_1 = []
        self.time_list_true = []
        self.time_list_false = []
        self.time_difference = []
        self.counter = 0  # Keep track of what number of voltagr step you are

        for (I_sensitivity, I_kinetics, t) in zip(
            self.fluorescence_trace_for_sensitivity,
            self.fluorescence_for_kinetics,
            self.time,
        ):
            # Only consider waveform data corresponding to t_waveform < t_fluorescence
            # Next step is to check if the data point in the signal belongs to the top or
            # bottom of the square wave
            self.filtered_matrix = self.waveform_time_matrix[
                self.waveform_time_matrix[:, 1] < t
            ]
            self.check = self.filtered_matrix[-1, 0]

            # If self.check = True, then data point belongs to top of square wave
            # we collect all the following data in a list untill a new step in the waveform
            # is reached. Then we pass on the data as a single isolated period to the empty
            # self.periods_fluorescence_sensitivity list
            if self.check:
                if len(self.fluorescence_list_false) != 0:
                    # Sent list to collection of subsets. To avoid doing every iteration,
                    # we empty the list again so that this conditional is not satisfied
                    self.periods_fluorescence_sensitivity.append(
                        np.array(self.fluorescence_list_false)
                    )
                    self.periods_fluorescence_kinetics.append(
                        np.array(self.fluorescence_list_false_1)
                    )
                    self.periods_time.append(np.array(self.time_list_false))

                    self.fluorescence_list_false = []
                    self.fluorescence_list_false_1 = []
                    self.time_list_false = []

                # Keep track of time difference
                if len(self.fluorescence_list_true) == 0:
                    self.time_difference.append(
                        abs(
                            self.waveform_time_matrix[self.step_idx[self.counter], 1]
                            - t
                        )
                    )

                    if t > self.time[0]:
                        self.counter += 1

                # Expand list as long as no new voltage step is reached
                self.fluorescence_list_true.append(I_sensitivity)
                self.fluorescence_list_true_1.append(I_kinetics)
                self.time_list_true.append(t)

            # Same procedure but not the recriprocal for self.check = False
            else:
                if len(self.fluorescence_list_true) != 0:
                    self.periods_fluorescence_sensitivity.append(
                        np.array(self.fluorescence_list_true)
                    )
                    self.periods_fluorescence_kinetics.append(
                        np.array(self.fluorescence_list_true_1)
                    )
                    self.periods_time.append(np.array(self.time_list_true))

                    self.fluorescence_list_true = []
                    self.fluorescence_list_true_1 = []
                    self.time_list_true = []

                if len(self.fluorescence_list_false) == 0:
                    self.time_difference.append(
                        abs(
                            self.waveform_time_matrix[self.step_idx[self.counter], 1]
                            - t
                        )
                    )

                    if t > self.time[0]:
                        self.counter += 1

                self.fluorescence_list_false.append(I_sensitivity)
                self.fluorescence_list_false_1.append(I_kinetics)
                self.time_list_false.append(t)

            # In the last iteration of the loop you send the subset with the following code
            if I_sensitivity == self.fluorescence_trace_for_sensitivity[-1]:
                self.periods_fluorescence_sensitivity.append(
                    np.array(self.fluorescence_list_false)
                )
                self.periods_fluorescence_kinetics.append(
                    np.array(self.fluorescence_list_false_1)
                )
                self.periods_time.append(np.array(self.time_list_false))

        # Retrieve the voltage step frequency.
        self.V_Hz = int(round((self.counter + 1) / 2) / self.total_time)
        print("Voltage step frequency is {}.".format(self.V_Hz))

        # Overwrite first value for correction
        self.time_difference[0] = abs(self.waveform_time_matrix[0, 1] - self.time[0])

        # Now tidy the data so that every isolated signal has the same length
        # Since the isolated signal are not equal in length we have to use the numpy.mask data
        # transformation to trim the rows. We do not consider data points that exceed
        # the minimum length of the rows.
        def TidyData(arrs):
            lens = [len(ii) for ii in arrs]
            arr = np.ma.empty((len(arrs), np.max(lens)))
            arr.mask = True
            for idx, l in enumerate(arrs):
                arr[idx, : len(l)] = l
            return arr[:, : np.min(lens)]

        self.periods_fluorescence_sensitivity = TidyData(
            self.periods_fluorescence_sensitivity
        )
        self.periods_fluorescence_kinetics = TidyData(
            self.periods_fluorescence_kinetics
        )
        self.periods_time = TidyData(self.periods_time)

    def TransformCurves(self):

        #### Initialize empty lists ####
        # vertical_translation       = will store vertical translations (flourescence elevation) for every isolated period
        # horizontal_translation     = will store horizontal translations (time lapse) for every isolated period
        # transformed_periods        = will store the isolated fluorescence signals after transformation
        # transformed_periods        = will store the isolated time signals after transformation
        # initial_fluorescence       = will store fluorescence signal at t = 0 for every isolated subset
        self.vertical_translation = []
        self.vertical_translation_kinetics = []
        self.horizontal_translation = []
        self.transformed_periods_fluorescence_sensitivity = []
        self.transformed_periods_fluorescence_kinetics = []
        self.transformed_periods_time = []

        # Apply transformations
        for ii in range(len(self.periods_fluorescence_sensitivity)):
            self.vertical_translation.append(
                np.mean(
                    self.periods_fluorescence_sensitivity[ii][
                        -round(0.4 * len(self.periods_fluorescence_sensitivity[ii])) :
                    ]
                )
            )

            self.vertical_translation_kinetics.append(
                np.mean(
                    self.periods_fluorescence_kinetics[ii][
                        -round(0.4 * len(self.periods_fluorescence_kinetics[ii])) :
                    ]
                )
            )

            self.horizontal_translation.append(
                self.periods_time[ii][0] - self.time_difference[ii]
            )

            self.transformed_periods_fluorescence_sensitivity.append(
                self.periods_fluorescence_sensitivity[ii]
                - self.vertical_translation[ii]
            )
            self.transformed_periods_fluorescence_kinetics.append(
                self.periods_fluorescence_kinetics[ii]
                - self.vertical_translation_kinetics[ii]
            )
            self.transformed_periods_time.append(
                self.periods_time[ii] - self.horizontal_translation[ii]
            )

        # Add signal at t=0 for every subset. Since this is not recorded due to the time difference we have to
        # manually add it
        self.transformed_periods_fluorescence_sensitivity = np.array(
            self.transformed_periods_fluorescence_sensitivity
        )
        self.transformed_periods_time = np.array(self.transformed_periods_time)
        self.initial_fluorescence = -np.diff(self.vertical_translation)
        self.initial_fluorescence = np.append(
            self.initial_fluorescence[1], self.initial_fluorescence
        ).reshape(len(self.periods_fluorescence_sensitivity), 1)

        self.transformed_periods_fluorescence_kinetics = np.array(
            self.transformed_periods_fluorescence_kinetics
        )
        self.initial_fluorescence_kinetics = -np.diff(
            self.vertical_translation_kinetics
        )
        self.initial_fluorescence_kinetics = np.append(
            self.initial_fluorescence_kinetics[1], self.initial_fluorescence_kinetics
        ).reshape(len(self.transformed_periods_fluorescence_kinetics), 1)

        self.transformed_periods_fluorescence_sensitivity = np.append(
            self.initial_fluorescence,
            self.transformed_periods_fluorescence_sensitivity,
            axis=1,
        )
        self.transformed_periods_fluorescence_kinetics = np.append(
            self.initial_fluorescence_kinetics,
            self.transformed_periods_fluorescence_kinetics,
            axis=1,
        )

        self.transformed_periods_time = np.append(
            np.zeros((len(self.periods_fluorescence_sensitivity), 1)),
            self.transformed_periods_time,
            axis=1,
        )

    def CurveAveraging(self):
        def normalize_array(array):
            max_value = np.amax(array)
            min_value = np.amin(array)
            for i in range(len(array)):
                array[i] = (array[i] - min_value) / (max_value - min_value)
            return array

        # The upswings belong to the even rows, and downswings to the odd rows
        self.fluorescence_upswing = self.transformed_periods_fluorescence_kinetics[::2]
        self.fluorescence_downswing = self.transformed_periods_fluorescence_kinetics[
            1::2
        ]

        self.time_upswing = self.transformed_periods_time[::2]
        self.time_downswing = self.transformed_periods_time[1::2]

        # Get average and standard deviation for upswing and downswing respectively
        self.avg_fluorescence_upswing = np.mean(
            self.fluorescence_upswing[self.skip :], axis=0
        )
        self.std_fluorescence_upswing = np.std(
            self.fluorescence_upswing[self.skip :], ddof=1, axis=0
        )

        self.avg_fluorescence_downswing = np.mean(
            self.fluorescence_downswing[self.skip :], axis=0
        )
        self.std_fluorescence_downswing = np.std(
            self.fluorescence_downswing[self.skip :], ddof=1, axis=0
        )

        self.avg_fluorescence_upswing_normalized = normalize_array(
            np.mean(self.fluorescence_upswing[self.skip :], axis=0)
        )
        self.std_fluorescence_upswing_normalized = np.std(
            normalize_array(self.fluorescence_upswing[self.skip :]), ddof=1, axis=0
        )

        self.avg_fluorescence_downswing_normalized = normalize_array(
            np.mean(self.fluorescence_downswing[self.skip :], axis=0)
        )
        self.std_fluorescence_downswing_normalized = np.std(
            normalize_array(self.fluorescence_downswing[self.skip :]), ddof=1, axis=0
        )

        self.avg_time_upswing = np.mean(self.time_upswing[self.skip :], axis=0)
        self.std_time_upswing = np.std(self.time_upswing[self.skip :], ddof=1, axis=0)

        self.avg_time_downswing = np.mean(self.time_downswing[self.skip :], axis=0)
        self.std_time_downswing = np.std(
            self.time_downswing[self.skip :], ddof=1, axis=0
        )

        # Stack the averaged signals on top of each other. This seems quite redundant, however is necessary to get it into
        # the right data format for the bi_exponential fit algorithm in the following ExponentialFitting() method.
        self.total_number_of_periods = self.total_time / (1 / self.V_Hz)
        self.transformed_periods_fluorescence_kinetics = np.tile(
            np.array([self.avg_fluorescence_upswing, self.avg_fluorescence_downswing]),
            (int(self.total_number_of_periods), 1),
        )
        self.transformed_periods_time = np.tile(
            np.array([self.avg_time_upswing, self.avg_time_downswing]),
            (int(self.total_number_of_periods), 1),
        )

        # #Vizualization of curve averaging (seperate)
        # fig4_1, ax_1 = plt.subplots(figsize=(8.0, 5.8))
        # p05, = ax_1.plot(self.avg_time_upswing*1000, self.avg_fluorescence_upswing_normalized, label = "Upswing", color='blue')
        # ax_1.fill_between(self.avg_time_upswing*1000, self.avg_fluorescence_upswing_normalized + self.std_fluorescence_upswing_normalized, self.avg_fluorescence_upswing_normalized - self.std_fluorescence_upswing_normalized, facecolor='blue', alpha=0.5)
        # ax_1.set_title("Upswing", size=14)
        # ax_1.set_ylabel('Fluorescence (a.u.)', fontsize = 11)
        # ax_1.set_xlabel('Time (ms)', fontsize = 11)
        # ax_1.spines['right'].set_visible(False)
        # ax_1.spines['top'].set_visible(False)
        # ax_1.xaxis.set_ticks_position('bottom')
        # ax_1.yaxis.set_ticks_position('left')
        # plt.show()
        # if self.main_directory != None:
        #     fig4_1.savefig((os.path.join(self.main_directory, 'Analysis results//Averaged upswing trace.png')), dpi=1000)

        # fig4_2, ax_2 = plt.subplots(figsize=(8.0, 5.8))
        # p06, = ax_2.plot(self.avg_time_downswing*1000, self.avg_fluorescence_downswing_normalized, label = "Downswing", color=(0.9, 0.4, 0))
        # ax_2.fill_between(self.avg_time_downswing*1000, self.avg_fluorescence_downswing_normalized + self.std_fluorescence_downswing_normalized, self.avg_fluorescence_downswing_normalized - self.std_fluorescence_downswing_normalized, facecolor=(0.9, 0.4, 0), alpha=0.5)
        # ax_2.set_title("Downswing", size=14)
        # ax_2.set_ylabel('Fluorescence (a.u.)', fontsize = 11)
        # ax_2.set_xlabel('Time (ms)', fontsize = 11)
        # ax_2.spines['right'].set_visible(False)
        # ax_2.spines['top'].set_visible(False)
        # ax_2.xaxis.set_ticks_position('bottom')
        # ax_2.yaxis.set_ticks_position('left')
        # plt.show()
        # if self.main_directory != None:
        #     fig4_2.savefig((os.path.join(self.main_directory, 'Analysis results//Averaged downswing trace.png')), dpi=1000)

    def fit_on_averaged_curve(self):

        # try:
        # Initialize figure before for-loop
        fig, ax = plt.subplots(figsize=(10.0, 8))

        # Bi-exponential function for the fitting algorithm

        # =============================================================================
        #     F(t) = A × (C × exp(–t/t1) + (1 – C) × exp(–t/t2)), where t1 was the time constant
        #     of the fast component and t2 was the time constant of the slow component. The
        #     percentage of the total magnitude that was associated with the fast component (%t1
        #     ) was defined as C above.
        # =============================================================================
        def func(t, A, t1, C, t2):
            return A * (C * np.exp(-(t / t1)) + (1 - C) * np.exp(-(t / t2)))

        parameter_bounds = ([-np.inf, 0, 0, 0], [np.inf, 0.1, 1, 0.1])

        # ============== Upswing =================

        # =============================================================================
        # Only the first 50 ms in the fluorescence rise and fluorescence decay segments
        # were used in the downstream bi-exponential fitting.
        # Here we have 5hz step, so first half will be 50 ms in time.
        # =============================================================================
        array_length = len(self.avg_time_upswing)
        self.avg_fluorescence_upswing = self.avg_fluorescence_upswing[
            : round(array_length / 2)
        ]
        self.avg_time_upswing = self.avg_time_upswing[: round(array_length / 2)]
        self.std_fluorescence_upswing = self.std_fluorescence_upswing[
            : round(array_length / 2)
        ]
        self.std_fluorescence_upswing = self.std_fluorescence_upswing[
            : round(array_length / 2)
        ]

        # Curve fitting of every isolated signal, similar to the photobleach algorithm
        popt, pcov = curve_fit(
            func,
            self.avg_time_upswing,
            self.avg_fluorescence_upswing,
            bounds=parameter_bounds,
            maxfev=500000,
        )

        # Find the fast and slow constant
        self.upswing_fast_constant = min([popt[1], popt[3]])
        self.upswing_slow_constant = max([popt[1], popt[3]])

        # Get the fast component percentage.
        if popt[1] > popt[3]:
            self.upswing_fast_component_percentage = 1 - popt[2]
        else:
            self.upswing_fast_component_percentage = popt[2]

        # Plot every isolated signal and its corresponding fit. Be aware of that when we apply CurveAveraging(), then
        # we have the same for every upswing and the same for every downswing. Neglect periods that we skip
        (p07,) = ax.plot(
            self.avg_time_upswing * 1000,
            self.avg_fluorescence_upswing,
            label="Experimental data",
            color="blue",
            alpha=0.5,
        )
        ax.fill_between(
            self.avg_time_upswing * 1000,
            self.avg_fluorescence_upswing + self.std_fluorescence_upswing,
            self.avg_fluorescence_upswing - self.std_fluorescence_upswing,
            facecolor="blue",
            alpha=0.5,
        )
        (p08,) = ax.plot(
            self.avg_time_upswing * 1000,
            func(self.avg_time_upswing, *popt),
            color=(0.9, 0, 0),
            label="Bi-exponential fit",
        )

        # Axis and labels for fig
        ax.set_title("Bi-exponential fitting of averaged up-swings", size=14)
        ax.set_ylabel("Fluorescence (a.u.)", fontsize=11)
        ax.set_xlabel("Time(ms)", fontsize=11)
        ax.legend(
            [p08, p07],
            [
                "Fit ({} ms/ {} ms, fast component percentage: {}%)".format(
                    str(self.upswing_fast_constant * 1000)[:5],
                    str(self.upswing_slow_constant * 1000)[:5],
                    str(self.upswing_fast_component_percentage * 100)[:5],
                ),
                "Experimental data",
            ],
        )
        ax.spines["right"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax.xaxis.set_ticks_position("bottom")
        ax.yaxis.set_ticks_position("left")
        plt.show()
        if self.main_directory != None:
            fig.savefig(
                (
                    os.path.join(
                        self.main_directory,
                        "Analysis results//Bi-exponential fitting of averaged up-swings.png",
                    )
                ),
                dpi=1200,
            )

        # ============== Downswing =================
        self.avg_fluorescence_downswing = self.avg_fluorescence_downswing[
            : round(array_length / 2)
        ]
        self.avg_time_downswing = self.avg_time_downswing[: round(array_length / 2)]
        self.std_fluorescence_downswing = self.std_fluorescence_downswing[
            : round(array_length / 2)
        ]
        self.std_fluorescence_downswing = self.std_fluorescence_downswing[
            : round(array_length / 2)
        ]

        # Initialize figure before for-loop
        fig2, ax2 = plt.subplots(figsize=(10.0, 8))

        # Curve fitting of every isolated signal, similar to the photobleach algorithm
        popt, pcov = curve_fit(
            func,
            self.avg_time_downswing,
            self.avg_fluorescence_downswing,
            bounds=parameter_bounds,
            maxfev=500000,
        )

        # Find the fast and slow constant
        self.downswing_fast_constant = min([popt[1], popt[3]])
        self.downswing_slow_constant = max([popt[1], popt[3]])

        # Get the fast component percentage.
        if popt[1] > popt[3]:
            self.downswing_fast_component_percentage = 1 - popt[2]
        else:
            self.downswing_fast_component_percentage = popt[2]

        # Plot every isolated signal and its corresponding fit. Be aware of that when we apply CurveAveraging(), then
        # we have the same for every upswing and the same for every downswing. Neglect periods that we skip
        (p09,) = ax2.plot(
            self.avg_time_downswing * 1000,
            self.avg_fluorescence_downswing,
            label="Experimental data",
            color=(0.9, 0.4, 0),
            alpha=0.5,
        )
        ax2.fill_between(
            self.avg_time_downswing * 1000,
            self.avg_fluorescence_downswing + self.std_fluorescence_downswing,
            self.avg_fluorescence_downswing - self.std_fluorescence_downswing,
            facecolor=(0.9, 0.4, 0),
            alpha=0.5,
        )
        (p10,) = ax2.plot(
            self.avg_time_downswing * 1000,
            func(self.avg_time_downswing, *popt),
            color=(0.9, 0, 0),
            label="Bi-exponential fit",
        )

        # Axis and labels for fig
        ax2.set_title("Bi-exponential fitting of averaged down-swings", size=14)
        ax2.set_ylabel("Fluorescence (a.u.)", fontsize=11)
        ax2.set_xlabel("Time(ms)", fontsize=11)
        ax2.legend(
            [p10, p09],
            [
                "Fit ({} ms/ {} ms, fast component percentage: {}%)".format(
                    str(self.downswing_fast_constant * 1000)[:5],
                    str(self.downswing_slow_constant * 1000)[:5],
                    str(self.downswing_fast_component_percentage * 100)[:5],
                ),
                "Experimental data",
            ],
        )
        ax2.spines["right"].set_visible(False)
        ax2.spines["top"].set_visible(False)
        ax2.xaxis.set_ticks_position("bottom")
        ax2.yaxis.set_ticks_position("left")
        plt.show()
        if self.main_directory != None:
            fig2.savefig(
                (
                    os.path.join(
                        self.main_directory,
                        "Analysis results//Bi-exponential fitting of averaged down-swings.png",
                    )
                ),
                dpi=1200,
            )
        # except:
        #     print('fit_on_averaged_curve failed.')

    def ExponentialFitting(self):

        # Intialize empty lists
        # bi_exponential_ratio       = will store amplitude of time constants
        # time_constant_parameters   = will store optimal time constants, extracted from parameters_fit
        # scaler_parameters          = will store optimal scaler paramters, extracted from parameters_fit
        self.bi_exponential_ratio = []
        self.time_constant_parameters = [[], []]
        self.scalar_parameters = [[], []]

        # Initialize figure before for-loop
        fig5, ax = plt.subplots(figsize=(12.0, 8))

        # Loop over every isolated period. For this reason we needed to stack the isolated periods
        # at the end of the CurveAveraging() method. Hence, this code also works for data that
        # is not averaged when you skip over the CurveAveraging method.
        for ii in range(len(self.periods_fluorescence_kinetics)):

            # Bi-exponential function for the fitting algorithm

            # F(t) = A × (C × exp(–t/t1) + (1 – C) × exp(–t/t2)), where t1 was the time constant
            # of the fast component and t2 was the time constant of the slow component. The
            # percentage of the total magnitude that was associated with the fast component (%t1
            # ) was defined as C above.
            def func(t, A, t1, C, t2):
                return A * (C * np.exp(-(t / t1)) + (1 - C) * np.exp(-(t / t2)))

            parameter_bounds = ([-np.inf, 0, 0, 0], [np.inf, 0.1, 1, 0.1])

            # =============================================================================
            # Only the first 50 ms in the fluorescence rise and fluorescence decay segments
            # were used in the downstream bi-exponential fitting.
            # Here we have 5hz step, so first half will be 50 ms in time.
            # =============================================================================
            array_length = len(self.avg_time_upswing)
            self.individual_period_for_fitting = (
                self.transformed_periods_fluorescence_kinetics[ii][
                    : round(array_length / 2)
                ]
            )
            self.individual_time = self.transformed_periods_time[ii][
                : round(array_length / 2)
            ]

            # Curve fitting of every isolated signal, similar to the photobleach algorithm
            popt, pcov = curve_fit(
                func,
                self.individual_time,
                self.individual_period_for_fitting,
                bounds=parameter_bounds,
                maxfev=500000,
            )

            # Find the fast and slow constant
            fast_constant = min([popt[1], popt[3]])
            slow_constant = max([popt[1], popt[3]])

            # Get the fast component percentage.
            if popt[1] > popt[3]:
                fast_component_percentage = 1 - popt[2]
            else:
                fast_component_percentage = popt[2]

            # Store optimal parameters in an ordered fashion. Similar reasoning as with the
            # photobleach
            self.bi_exponential_ratio.append(fast_component_percentage)

            self.time_constant_parameters[0].append(fast_constant)
            self.time_constant_parameters[1].append(slow_constant)

            self.scalar_parameters[0].append(popt[0])
            self.scalar_parameters[1].append(popt[2])

            # Plot every isolated signal and its corresponding fit. Be aware of that when we apply CurveAveraging(), then
            # we have the same for every upswing and the same for every downswing. Neglect periods that we skip
            (p07,) = ax.plot(
                self.periods_time[ii],
                self.periods_fluorescence_kinetics[ii],
                linestyle="None",
                marker="o",
                markersize=2,
                markerfacecolor=(0, 0, 0.9),
                label="Experimental data",
            )
            if ii > self.skip:
                (p08,) = ax.plot(
                    self.transformed_periods_time[ii] + self.horizontal_translation[ii],
                    func(self.transformed_periods_time[ii], *popt)
                    + self.vertical_translation_kinetics[ii],
                    color=(0.9, 0, 0),
                    label="Bi-exponential fit",
                )

        # Axis and labels for fig5
        ax.set_ylabel("Fluorescence (a.u.)", fontsize=11)
        ax.set_xlabel("Time(s)", fontsize=11)
        ax.legend([p08, p07], ["Bi-exponential fit", "Experimental data"])
        ax.spines["right"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax.xaxis.set_ticks_position("bottom")
        ax.yaxis.set_ticks_position("left")
        plt.show()
        if self.main_directory != None:
            fig5.savefig(
                (
                    os.path.join(
                        self.main_directory,
                        "Analysis results//Exponential fit trace.png",
                    )
                ),
                dpi=1200,
            )

    def extract_sensitivity(self):

        # =============================================================================
        # Fluorescence changes to voltage steps were calculated as Δ F/F = (Fss – Fbl)/Fbl ,
        # where Fss(steady-state fluorescence) is the mean fluorescence intensity averaged
        # over 50-70 ms during a voltage step after the fluorescence signal reaches
        # its plateau, and Fbl(baseline fluorescence) is the mean fluorescence intensity
        # averaged over 100 ms before the voltage step.
        # =============================================================================

        self.upper_step_values = []
        self.lower_step_values = []

        # In individual period, which part percentage wise is seen as steady state.
        self.steady_state_region = [0.4, 0.9]

        # Initialize figure before for-loop
        fig6, ax = plt.subplots(figsize=(12.0, 8))

        # Loop over every isolated period. For this reason we needed to stack the isolated periods
        # at the end of the CurveAveraging() method. Hence, this code also works for data that
        # is not averaged when you skip over the CurveAveraging method.
        for ii in range(len(self.periods_fluorescence_sensitivity)):

            period_length = len(self.periods_fluorescence_sensitivity[ii])

            # Upswings period
            if (ii % 2) == 0:
                steady_region_segment = self.periods_fluorescence_sensitivity[ii][
                    round(period_length * self.steady_state_region[0]) : round(
                        period_length * self.steady_state_region[1]
                    )
                ]
                if ii > self.skip:
                    self.upper_step_values.append(np.mean(steady_region_segment))
            # Down-swing period.
            else:
                steady_region_segment = self.periods_fluorescence_sensitivity[ii][
                    round(period_length * self.steady_state_region[0]) : round(
                        period_length * self.steady_state_region[1]
                    )
                ]
                if ii > self.skip:
                    self.lower_step_values.append(np.mean(steady_region_segment))

            # Plot every isolated signal and its corresponding fit. Be aware of that when we apply CurveAveraging(), then
            # we have the same for every upswing and the same for every downswing. Neglect periods that we skip
            (p07,) = ax.plot(
                self.periods_time[ii],
                self.periods_fluorescence_sensitivity[ii],
                linestyle="None",
                marker="o",
                markersize=2,
                markerfacecolor=(0, 0, 0.9),
                label="Experimental data",
            )
            if ii > self.skip:
                (p08,) = ax.plot(
                    self.transformed_periods_time[ii][0 : len(steady_region_segment)]
                    + len(self.periods_time[ii])
                    / self.camera_fps
                    * (self.steady_state_region[0])
                    + self.horizontal_translation[ii],
                    steady_region_segment,
                    color=(0.9, 0, 0),
                    label="Region of calculation",
                )

        # Calculate the Δ F/F
        self.intensity_ratio = np.true_divide(
            np.array(self.upper_step_values) - np.array(self.lower_step_values),
            np.array(self.lower_step_values),
        )
        self.avg_intensity_ratio = np.mean(self.intensity_ratio)
        self.std_intensity_ratio = np.std(self.intensity_ratio, ddof=1)

        # Axis and labels for fig5
        ax.set_ylabel("Fluorescence (a.u.)", fontsize=11)
        ax.set_xlabel("Time(s)", fontsize=11)
        ax.legend(
            [p08, p07],
            [
                "Sensitivity: {}% +/- {}%".format(
                    str(round(self.avg_intensity_ratio * 100, 2)),
                    str(round(self.std_intensity_ratio * 100, 2)),
                ),
                "Experimental data",
            ],
        )
        ax.spines["right"].set_visible(False)
        ax.spines["top"].set_visible(False)
        ax.xaxis.set_ticks_position("bottom")
        ax.yaxis.set_ticks_position("left")
        plt.show()
        if self.main_directory != None:
            fig6.savefig(
                (
                    os.path.join(
                        self.main_directory,
                        "Analysis results//Sensitivity calculation region.png",
                    )
                ),
                dpi=1200,
            )

    def Statistics(self):

        # Data transformation to put it in a nice Numpy format
        self.time_constant_parameters = np.array(
            self.time_constant_parameters.copy()
        ).transpose()

        self.time_constant_upswing = self.time_constant_parameters[::2, :]
        self.time_constant_downswing = self.time_constant_parameters[1::2, :]

        # delta F/F and steady-state fluorescence values, not normalized
        # self.vertical_translation[::2]: The upper step values.
        # self.vertical_translation[1::2]: The lower step values.
        # self.intensity_ratio = np.true_divide(np.array(self.vertical_translation[::2]) - np.array(self.vertical_translation[1::2]), np.array(self.vertical_translation[1::2]))

        # self.intensity_ratio = np.true_divide(self.vertical_translation[::2], self.vertical_translation[1::2])
        # self.avg_intensity_ratio = np.mean(self.intensity_ratio[self.skip:])
        # self.std_intensity_ratio = np.std(self.intensity_ratio[self.skip:], ddof=1)
        # self.DeltaF = f'{self.avg_intensity_ratio:.6f} +/- {self.std_intensity_ratio:.6f}'

        # Amplitude of fast time constant
        # Upswing
        self.avg_bi_exponential_ratio_upswing = np.mean(
            self.bi_exponential_ratio[::2][self.skip :]
        )
        self.std_bi_exponential_ratio_upswing = np.std(
            self.bi_exponential_ratio[::2][self.skip :], ddof=1
        )
        self.amplitude_upswing = f"{self.avg_bi_exponential_ratio_upswing:.6f} +/- {self.std_bi_exponential_ratio_upswing:.6f}"

        # Downswing
        self.avg_bi_exponential_ratio_downswing = np.mean(
            self.bi_exponential_ratio[1::2][self.skip :]
        )
        self.std_bi_exponential_ratio_downswing = np.std(
            self.bi_exponential_ratio[1::2][self.skip :], ddof=1
        )
        self.amplitude_downswing = f"{self.avg_bi_exponential_ratio_downswing:.6f} +/- {self.std_bi_exponential_ratio_downswing:.6f}"

        # Time constant statistics
        # Upswing
        self.avg_fast_time_constant_upswing = np.mean(
            self.time_constant_upswing[self.skip :, 0]
        )
        self.std_fast_time_constant_upswing = np.std(
            self.time_constant_upswing[self.skip :, 0], ddof=1
        )
        self.fastconstant_upswing = f"{self.avg_fast_time_constant_upswing:.6f} +/- {self.std_fast_time_constant_upswing:.6f}"

        self.avg_slow_time_constant_upswing = np.mean(
            self.time_constant_upswing[self.skip :, 1]
        )
        self.std_slow_time_constant_upswing = np.std(
            self.time_constant_upswing[self.skip :, 1], ddof=1
        )
        self.slowconstant_upswing = f"{self.avg_slow_time_constant_upswing:.6f} +/- {self.std_slow_time_constant_upswing:.6f}"

        # Downswing
        self.avg_fast_time_constant_downswing = np.mean(
            self.time_constant_downswing[self.skip :, 0]
        )
        self.std_fast_time_constant_downswing = np.std(
            self.time_constant_downswing[self.skip :, 0], ddof=1
        )
        self.fastconstant_downswing = f"{self.avg_fast_time_constant_downswing:.6f} +/- {self.std_fast_time_constant_downswing:.6f}"

        self.avg_slow_time_constant_downswing = np.mean(
            self.time_constant_downswing[self.skip :, 1]
        )
        self.std_slow_time_constant_downswing = np.std(
            self.time_constant_downswing[self.skip :, 1], ddof=1
        )
        self.slowconstant_downswing = f"{self.avg_slow_time_constant_downswing:.6f} +/- {self.std_slow_time_constant_downswing:.6f}"

        self.statistics_test = (
            "\n"
            + "STATISTICS FOR SUBSET FIT"
            + "\n"
            + "---------------------------------------------------"
            + "\n"
            + "dF/F (normalized)    = "
            + str(round(self.avg_intensity_ratio * 100, 4))
            + "% +/- "
            + str(round(self.std_intensity_ratio * 100, 4))
            + "%\n"
            + "\n"
            + "Upswing"
            + "\n"
            + "t_fast up                = "
            + str(self.upswing_fast_constant)[:8]
            + " s, "
            + str(self.upswing_fast_component_percentage * 100)[:5]
            + "%\n"
            + "t_slow up                = "
            + str(self.upswing_slow_constant)[:8]
            + " s"
            + "\n"
            + "Amplitude up             = "
            + self.amplitude_upswing
            + "\n"
            + "\n"
            + "Downswing"
            + "\n"
            + "t_fast down              = "
            + str(self.downswing_fast_constant)[:8]
            + " s, "
            + str(self.downswing_fast_component_percentage * 100)[:5]
            + "%\n"
            + "t_slow down              = "
            + str(self.downswing_slow_constant)[:8]
            + " s, "
            + "\n"
            + "Amplitude down           = "
            + self.amplitude_downswing
            + "\n"
            + "\n"
            + "STATISTICS FOR PHOTOBLEACH"
            + "\n"
            + "---------------------------------------------------"
            + "\n"
            + "t1                       = "
            + f"{self.photobleach_t1:.6f}"
            + " s"
            + "\n"
            + "a                        = "
            + f"{self.photobleach_a:.6f}"
            + "\n"
            + "t2                       = "
            + f"{self.photobleach_t2:.6f}"
            + " s"
            + "\n"
            + "b                        = "
            + f"{self.photobleach_b:.6f}"
            + "\n"
            + "ratio1                   = "
            + f"{self.photobleach_ratio1:.6f}"
            + "\n"
            + "ratio2                   = "
            + f"{self.photobleach_ratio2:.6f}"
            + "\n"
        )

        print(self.statistics_test)
        if self.main_directory != None:
            with open(
                os.path.join(
                    self.main_directory,
                    "Analysis results//Statistics (sensitivity {}).txt".format(
                        str(round(self.avg_intensity_ratio * 100, 4))
                    ),
                ),
                "w",
            ) as output_file:
                output_file.write(self.statistics_test)

        return (
            self.avg_fast_time_constant_upswing,
            self.avg_slow_time_constant_upswing,
            self.avg_bi_exponential_ratio_upswing,
            self.avg_fast_time_constant_downswing,
            self.avg_slow_time_constant_downswing,
            self.avg_bi_exponential_ratio_downswing,
            self.avg_intensity_ratio,
            self.std_intensity_ratio,
        )

    def Normalization(self, V0, V1, V0_reference, V1_reference):

        # Assumtion that the fluorescence signal, F(V), is linear with V
        # self.V0, self.V1, self.V0_reference, self.V1_reference = [int(x) for x in input('V0 V1 V0_reference V1_reference ').split()]
        self.V0, self.V1, self.V0_reference, self.V1_reference = (
            V0,
            V1,
            V0_reference,
            V1_reference,
        )

        self.dV = self.V1 - self.V0
        self.dF = np.array(self.vertical_translation[::2]) - np.array(
            self.vertical_translation[1::2]
        )

        self.topdiff = self.V1_reference - self.V1
        self.lowdiff = self.V0_reference - self.V0

        self.slope = self.dF / self.dV

        self.F1 = self.vertical_translation[::2] + self.slope * self.topdiff
        self.F0 = self.vertical_translation[1::2] + self.slope * self.lowdiff

        self.intensity_ratio = self.F1 / self.F0

        self.avg_intensity_ratio = np.mean(self.intensity_ratio[self.skip :])
        self.std_intensity_ratio = np.std(self.intensity_ratio[self.skip :], ddof=1)

        print(self.avg_intensity_ratio)
        return self.avg_intensity_ratio, self.std_intensity_ratio




if __name__ == "__main__":
    from skimage.io import imread
    import time
    from IPython import get_ipython

    #    speedGalvo = 20000.0 #Volt/s
    #    AccelerationGalvo = 1.54*10**8 #Acceleration galvo in volt/s^2
    #    #--------------------------------------------------------------------------
    #    PMT_image = imread(r'D:\XinMeng\imageCollection\Round2_Coord3_R1500C1500_PMT_2.tif', as_gray=True)
    ##    time_gap = 1/50000
    #
    #    RegionProposalMask, RegionProposalOriginalImage = ProcessImage.generate_mask(PMT_image, openingfactor=2,
    #                                                                                                closingfactor=4, binary_adaptive_block_size=335)#256(151) 500(335)
    #
    #    CellSkeletonizedContourDict= ProcessImage.get_Skeletonized_contour(PMT_image, RegionProposalMask, smallest_size=400, contour_thres=0.001,
    #                                                                                       contour_dilationparameter=11, cell_region_opening_factor=1, cell_region_closing_factor=2,
    #                                                                                       scanning_voltage=5, points_per_contour=500, sampling_rate = 50000)

    # =============================================================================
    # =============================================================================
    #     tag_folder = r'M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\2020-05-12 Archon lib 400FOVs 4 grid\trial_1'
    #     lib_folder = r'D:\XinMeng\imageCollection\Fov3\New folder (3)'
    #   #   tag_folder = r'M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\2020-3-6 Archon brightness screening\NovArch library'
    #
    #     tag_round = 'Round1'
    #     lib_round = 'Round4'
    #
    #     EvaluatingPara_1 = 'Mean intensity divided by tag'
    #     EvaluatingPara_2 = 'Contour soma ratio'
    #
    #     MeanIntensityThreshold = 0.16
    #
    #     starttime = time.time()
    #
    #     tagprotein_cell_properties_dict = ProcessImage.TagFluorescenceAnalysis(tag_folder, tag_round, Roundness_threshold = 2.1)
    #     print('tag done.')
    #
    #     tagprotein_cell_properties_dict_meanIntensity_list = []
    #     for eachpos in tagprotein_cell_properties_dict:
    #         for i in range(len(tagprotein_cell_properties_dict[eachpos])):
    #             tagprotein_cell_properties_dict_meanIntensity_list.append(tagprotein_cell_properties_dict[eachpos]['Mean intensity'][i])
    # =============================================================================
    stitch_img = False
    retrievefocus_map = False
    find_focus = False
    registration = False
    merge_dataFrames = False
    cam_screening_analysis = False
    photo_current = True

    if stitch_img == True:
        Nest_data_directory = r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\Evolution screening\2020-12-19_2020-12-19_18-41-18_Lib9_Q1_1TO16_NOPURO"
        Stitched_image_dict = ProcessImage.image_stitching(
            Nest_data_directory, row_data_folder=True
        )

        for key in Stitched_image_dict:
            r2 = Stitched_image_dict[key]
            row_image = Image.fromarray(r2)
            row_image.save(
                os.path.join(Nest_data_directory, "{} stitched.tif".format(key))
            )

    elif retrievefocus_map == True:
        Nest_data_directory = r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\Evolution screening\2020-11-5 Lib z3_2p5um 9coords AF gap3"
        focus_map_dict = ProcessImage.retrieve_focus_map(Nest_data_directory)

    elif find_focus == True:
        ProcessImage.find_infocus_from_stack(
            r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\Evolution screening\2020-11-05_2020-11-05_22-20-31_WT z3 gap3"
        )

    elif registration == True:
        data_1_xlsx = pd.ExcelFile(
            r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\Evolution screening\2020-11-17 photobleaching WT LentiII\Round2_2020-11-20_17-29-19_CellsProperties.xlsx"
        )
        data_1 = pd.read_excel(data_1_xlsx)
        data_2_xlsx = pd.ExcelFile(
            r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\Evolution screening\2020-11-17 photobleaching WT LentiII\Round3_2020-11-20_17-32-28_CellsProperties.xlsx"
        )
        data_2 = pd.read_excel(data_2_xlsx)
        data_3_xlsx = pd.ExcelFile(
            r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\Evolution screening\2020-11-17 photobleaching WT LentiII\Round4_2020-11-20_17-35-24_CellsProperties.xlsx"
        )
        data_3 = pd.read_excel(data_3_xlsx)

        registered_dataframe = ProcessImage.Register_cells([data_1, data_2, data_3])
        # registered_dataframe = ProcessImage.Register_between_dataframes(data_1, data_2)
    # else:
    #     res,diff = ProcessImage.find_repeat_imgs(r'M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\Evolution screening\2020-11-24_2020-11-24_16-45-26_2rounds_GFP_olddish', similarity_thres = 400)
    elif merge_dataFrames == True:
        data_1_xlsx = pd.ExcelFile(
            r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\Evolution screening\2021-01-27 Lib8 Archon KCl 8b8 ND1p5ND0p3\m1.xlsx"
        )
        data_1 = pd.read_excel(data_1_xlsx)
        data_2_xlsx = pd.ExcelFile(
            r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\Evolution screening\2021-01-27 Lib8 Archon KCl 8b8 ND1p5ND0p3\m2.xlsx"
        )
        data_2 = pd.read_excel(data_2_xlsx)

        print("Start Cell_DataFrame_Merging.")
        Cell_DataFrame_Merged = ProcessImage.MergeDataFrames(
            data_1, data_2, method="Kcl"
        )
        print("Cell_DataFrame_Merged.")

        DataFrames_filtered = ProcessImage.FilterDataFrames(
            Cell_DataFrame_Merged, 0.2, 1
        )
        DataFrames_filtered.to_excel(
            r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\Evolution screening\2021-01-27 Lib8 Archon KCl 8b8 ND1p5ND0p3\m3.xlsx"
        )
        # DataFrame_sorted = ProcessImage.Sorting_onTwoaxes(DataFrames_filtered, 'KC_EC_Mean_intensity_in_contour_ratio', 'Mean_intensity_in_contour_Lib_EC', 0, 1)

    elif cam_screening_analysis == True:
        ProcessImage.cam_screening_post_processing(
            r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Delizzia\2020-11-19_2020-11-19_10-14-32_trial_cam_screen"
        )
        
    elif photo_current == True:
        ProcessImage.PhotoCurrent(r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Patch clamp\2021-03-30 GR D121E\cell3\photocurrent")
