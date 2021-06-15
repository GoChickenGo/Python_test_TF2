# -*- coding: utf-8 -*-
"""
Created on Thu May  7 15:50:10 2020

@author: xinmeng
"""

import numpy as np
import matplotlib.pyplot as plt
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
)
import skimage.external.tifffile as skimtiff
from datetime import datetime
from skimage.io import imread
import os
import plotly.express as px

# Ensure that the Widget can be run either independently or as part of Tupolev.
if __name__ == "__main__":
    abspath = os.path.abspath(__file__)
    dname = os.path.dirname(abspath)
    os.chdir(dname + "/../")

# ----------------------------------TF-2----------------------------------------

from MaskRCNN.Configurations.ConfigFileInferenceOld import cellConfig
from MaskRCNN.Engine.MaskRCNN import MaskRCNN as modellib
import MaskRCNN.Miscellaneous.visualize as visualize
from ImageAnalysis.ImageProcessing import ProcessImage

# ================================================================ProcessImage===============================================
class ProcessImageML:
    def __init__(
        self,
        WeigthPath=r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Martijn\FinalResults\ModelWeights.h5",
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        """
        # =============================================================================
        # Initialize the detector instance and load the model.
        # =============================================================================
        """
        # Load configuration file
        # Setup config file
        self.config = cellConfig()
        self.config.LogDir = ""
        self.config.CCoor_STD_DEV = 0.1
        # self.config.WeigthPath = r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Martijn\SpikingHek.h5"
        self.config.WeigthPath = WeigthPath

        # These four setting use the old configurations. The results are slightly different due to scaling.
        # However the new version will prevent any OOM erros from occuring
        # config.IMAGE_MIN_SCALE = 2.0
        # config.IMAGE_MIN_DIM = 1024
        # config.IMAGE_MAX_DIM = 1024
        # config.IMAGE_RESIZE_MODE = "pad64"

        # If you use spiking hek images, uncomment the next lines, and use:
        # Image = skimage.transform.resize(Image,[1024,1024],preserve_range=True).astype(Image.dtype)
        # config.IMAGE_RESIZE_MODE = "square"
        # config.IMAGE_MIN_DIM = 1024
        # config.IMAGE_MAX_DIM = 1024
        # config.IMAGE_MIN_SCALE = 1

        # Create model
        self.Detector = modellib(self.config, "inference", model_dir=self.config.LogDir)
        self.Detector.compileModel()
        # print(self.config.WeigthPath)
        self.Detector.LoadWeigths(self.config.WeigthPath, by_name=True)

    #%%
    """
    # ======================================================================================================================
    # ************************************  Retrive scanning scheme and read in images. ************************************ 
    # ======================================================================================================================
    """

    def ReadinImgs_Roundstack(self, Nest_data_directory, rowIndex, colIndex):
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
            temp_loaded_image = imread(img_fileName, as_gray=False)
            temp_loaded_image = temp_loaded_image[np.newaxis, :, :]
            if ImgSequenceNum == 1:
                PMT_image_wholetrace_stack = temp_loaded_image
            else:
                PMT_image_wholetrace_stack = np.concatenate(
                    (PMT_image_wholetrace_stack, temp_loaded_image), axis=0
                )

        return PMT_image_wholetrace_stack

    def retrive_scanning_scheme(self, Nest_data_directory, file_keyword="PMT_0Zmax"):
        """
        Return lists that contain round sequence and coordinates strings, like ['Coords1_R0C0', 'Coords2_R0C1500']

        Parameters
        ----------
        Nest_data_directory : string.
            The directory to folder where the screening data is stored.
        file_keyword : string.
            The keyowrd used to search for file name.

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
        #        ImgSequenceNum = 0
        for file in os.listdir(Nest_data_directory):
            if file_keyword in file:
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

            CoordinatesList.append(
                eachfilename[eachfilename.index("Coord") : eachfilename.index("_PMT")]
            )
            CoordinatesList = list(dict.fromkeys(CoordinatesList))

        #        print(RoundNumberList, CoordinatesList, fileNameList)
        return RoundNumberList, CoordinatesList, fileNameList

    #%%
    """
    # ================================================================================================================
    # ************************************  Run detection on single image  ************************************* 
    # ================================================================================================================
    """

    def DetectionOnImage(self, Rawimage, axis=None, show_result=False):
        """
        Convert image pixel values to unit8 to run on MaskRCNN, and then run MaskRCNN on it.
        """
        # image = ProcessImage.convert_for_MaskRCNN(Rawimage)

        # Run the detection on input image.
        results = self.Detector.detect([Rawimage])

        MLresults = results[0]

        if show_result == True:

            # Set class_names = [None,None,None,None] to mute class name display.
            visualize.display_instances(
                Rawimage,
                MLresults["rois"],
                MLresults["masks"],
                MLresults["class_ids"],
                class_names=[None, None, None, None],
                centre_coors=MLresults["Centre_coor"],
                Centre_coor_radius=2,
                WhiteSpace=(0, 0),
            )  # MLresults['class_ids'],MLresults['scores'],

        if axis != None:
            # If axis is given, draw on axis.
            visualize.display_instances(
                Rawimage,
                MLresults["rois"],
                MLresults["masks"],
                MLresults["class_ids"],
                ["BG"] + self.config.ValidLabels,
                ax=axis,
                centre_coors=MLresults["Centre_coor"],
                Centre_coor_radius=2,
                WhiteSpace=(0, 0),
            )  # MLresults['class_ids'],MLresults['scores'],
            # ax.imshow(fig)

            return MLresults
        else:
            return MLresults

    """
    # ================================================================================================================
    # ************************************  Organize cell properties dictionary  ************************************* 
    # ================================================================================================================
    """

    def FluorescenceAnalysis(self, folder, round_num, save_mask=True):
        """
        # =============================================================================
        # Given the folder and round number, return a dictionary for the round
        # that contains each scanning position as key and structured array of detailed
        # information about each identified cell as content.
        #
        #   Returned structured array fields:
        #   - BoundingBox of cell ROI
        #   - Mean intensity of whole cell area
        #   - Mean intensity of cell membrane part
        #   - Contour soma ratio
        # =============================================================================

        Parameters
        ----------
        folder : string.
            The directory to folder where the screening data is stored.
        round_num : string.
            The target round number of analysis.
        save_mask: bool.
            Whether to save segmentation masks.

        Returns
        -------
        cell_Data : pd.DataFrame.
            Sum of return from func: retrieveDataFromML, for whole round.
        """
        RoundNumberList, CoordinatesList, fileNameList = self.retrive_scanning_scheme(
            folder, file_keyword="Zmax"
        )
        # RoundNumberList, CoordinatesList, fileNameList = self.retrive_scanning_scheme(folder, file_keyword = 'Zfocus')

        if not os.path.exists(os.path.join(folder, "MLimages_{}".format(round_num))):
            # If the folder is not there, create the folder
            os.mkdir(os.path.join(folder, "MLimages_{}".format(round_num)))

        for EachRound in RoundNumberList:

            cells_counted_in_round = 0

            if EachRound == round_num:

                # Start numbering cells at each round
                self.cell_counted_inRound = 0

                for EachCoord in CoordinatesList:

                    # =============================================================================
                    #             For tag fluorescence:
                    # =============================================================================
                    print(EachCoord)
                    # -------------- readin image---------------
                    for Eachfilename in enumerate(fileNameList):
                        if (
                            EachCoord in Eachfilename[1]
                            and EachRound in Eachfilename[1]
                        ):
                            if "0Zmax" in Eachfilename[1]:
                                ImgNameInfor = Eachfilename[1][
                                    0 : len(Eachfilename[1]) - 14
                                ]  # get rid of '_PMT_0Zmax.tif' in the name.
                            elif "0Zfocus" in Eachfilename[1]:
                                ImgNameInfor = Eachfilename[1][
                                    0 : len(Eachfilename[1]) - 16
                                ]  # get rid of '_PMT_0Zfocus.tif' in the name.
                            _imagefilename = os.path.join(folder, Eachfilename[1])
                    # ------------------------------------------

                    # =========================================================================
                    #                     USING MASKRCNN...
                    # =========================================================================
                    # Imagepath      = self.Detector._fixPathName(_imagefilename)
                    Rawimage = imread(_imagefilename)

                    #                    if ClearImgBef == True:
                    #                        # Clear out junk parts to make it esaier for ML detection.
                    #                        RawimageCleared = self.preProcessMLimg(Rawimage, smallest_size=300, lowest_region_intensity=0.16)
                    #                    else:
                    #                        RawimageCleared = Rawimage.copy()

                    image = ProcessImage.convert_for_MaskRCNN(Rawimage)

                    # Run the detection on input image.
                    results = self.Detector.detect([image])

                    MLresults = results[0]

                    if save_mask == True:
                        fig, ax = plt.subplots()
                        # Set class_names = [None,None,None,None] to mute class name display.
                        visualize.display_instances(
                            image,
                            MLresults["rois"],
                            MLresults["masks"],
                            MLresults["class_ids"],
                            class_names=[None, None, None, None],
                            ax=ax,
                            centre_coors=MLresults["Centre_coor"],
                            Centre_coor_radius=2,
                            WhiteSpace=(0, 0),
                        )  # MLresults['class_ids'],MLresults['scores'],
                        # ax.imshow(fig)
                        fig.tight_layout()
                        # Save the detection image
                        fig_name = os.path.join(
                            folder, "MLimages_{}\{}.tif".format(round_num, ImgNameInfor)
                        )
                        plt.savefig(
                            fname=fig_name, dpi=200, pad_inches=0.0, bbox_inches="tight"
                        )

                    # segmentationImg = Image.fromarray(fig) #generate an image object
                    # segmentationImg.save(os.path.join(folder, 'MLimages_{}\{}.tif'.format(round_num, ImgNameInfor)))#save as tif

                    if self.cell_counted_inRound == 0:
                        (
                            cell_Data,
                            self.cell_counted_inRound,
                            total_cells_counted_in_coord,
                        ) = ProcessImage.retrieveDataFromML(
                            Rawimage,
                            MLresults,
                            str(ImgNameInfor),
                            self.cell_counted_inRound,
                        )
                    else:
                        (
                            Cell_Data_new,
                            self.cell_counted_inRound,
                            total_cells_counted_in_coord,
                        ) = ProcessImage.retrieveDataFromML(
                            Rawimage,
                            MLresults,
                            str(ImgNameInfor),
                            self.cell_counted_inRound,
                        )
                        if len(Cell_Data_new) > 0:
                            cell_Data = cell_Data.append(Cell_Data_new)

                    # Count in total how many flat and round cells are identified.
                    cells_counted_in_round += total_cells_counted_in_coord

                print(
                    "Number of round/flat cells in this round: {}".format(
                        cells_counted_in_round
                    )
                )

        # Save to excel
        cell_Data.to_excel(
            os.path.join(
                os.path.join(
                    folder,
                    round_num
                    + "_"
                    + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    + "_CellsProperties.xlsx",
                )
            )
        )

        return cell_Data

    def analyze_single_image(
        self, Rawimage, axis=None, show_result=True, show_each_cell=False
    ):

        MLresults = self.DetectionOnImage(Rawimage, axis=axis, show_result=show_result)

        (
            cell_Data,
            cell_counted_inRound,
            total_cells_counted_in_coord,
        ) = ProcessImage.retrieveDataFromML(
            Rawimage, MLresults, show_each_cell=show_each_cell
        )

        print("Number of cells counted so far: {}".format(cell_counted_inRound))
        print(
            "Number of cells counted in image: {}".format(total_cells_counted_in_coord)
        )

        return cell_Data

    def analyze_images_in_folder(
        self,
        folder,
        generate_zmax=False,
        show_result=True,
        save_mask=True,
        save_excel=True,
    ):
        """
        Given the folder, perform general analysis over the images in it.

        Parameters
        ----------
        folder : str
            Path to the folder.
        generate_zmax : bool, optional
            Whether to calcaulate the z-max projection first. The default is False.
        show_result : bool, optional
            If show the machine learning segmentation results. The default is True.
        save_mask : bool, optional
            DESCRIPTION. The default is True.
        save_excel : bool, optional
            DESCRIPTION. The default is True.

        Returns
        -------
        cell_Data : pd.dataframe
            DESCRIPTION.

        """
        flat_cell_counted_in_folder = 0
        total_cells_counted_in_folder = 0
        background_substraction = False
        root_folder = folder

        # If need to do zmax projection first
        if generate_zmax == True:
            ProcessImage.cam_screening_post_processing(root_folder)
            # Here a new folder for maxProjection is generated inside, change the path
            folder = os.path.join(root_folder, "maxProjection")

        # If background images are taken
        if os.path.exists(os.path.join(root_folder, "background")):
            # If the background image is taken to substract out
            background_substraction = True
            print("Run background substraction.")

            # Get all the background files names
            background_fileNameList = []
            for file in os.listdir(os.path.join(root_folder, "background")):
                if "tif" in file and "calculated background" not in file:
                    background_fileNameList.append(
                        os.path.join(root_folder, "background", file)
                    )

            background_image = ProcessImage.image_stack_calculation(
                background_fileNameList, operation="mean"
            )

            # Save the individual file.
            with skimtiff.TiffWriter(
                os.path.join(root_folder, "background", "calculated background.tif"),
                imagej=True,
            ) as tif:
                tif.save(background_image.astype(np.int16), compress=0)

        # Get a list of file names
        fileNameList = []
        for file in os.listdir(folder):
            if "tif" in file and "LED" not in file:
                fileNameList.append(file)

        print(fileNameList)

        # Analyse each image
        for image_file_name in fileNameList:
            print(image_file_name)
            Rawimage = imread(os.path.join(folder, image_file_name))

            if background_substraction == True:
                Rawimage = np.abs(Rawimage - background_image)

            # Analyze each image
            # Run the detection on input image.
            MLresults = self.DetectionOnImage(
                Rawimage, axis=None, show_result=show_result
            )

            if save_mask == True:

                if not os.path.exists(os.path.join(folder, "ML_masks")):
                    # If the folder is not there, create the folder
                    os.mkdir(os.path.join(folder, "ML_masks"))

                fig, ax = plt.subplots()
                # Set class_names = [None,None,None,None] to mute class name display.
                visualize.display_instances(
                    Rawimage,
                    MLresults["rois"],
                    MLresults["masks"],
                    MLresults["class_ids"],
                    class_names=[None, None, None, None],
                    ax=ax,
                    centre_coors=MLresults["Centre_coor"],
                    Centre_coor_radius=2,
                    WhiteSpace=(0, 0),
                )  # MLresults['class_ids'],MLresults['scores'],
                # ax.imshow(fig)
                fig.tight_layout()
                # Save the detection Rawimage
                fig_name = os.path.join(
                    folder,
                    "ML_masks",
                    "ML_mask_{}.png".format(
                        image_file_name[0 : len(image_file_name) - 4]
                    ),
                )
                plt.savefig(
                    fname=fig_name, dpi=200, pad_inches=0.0, bbox_inches="tight"
                )

            if flat_cell_counted_in_folder == 0:
                (
                    cell_Data,
                    flat_cell_counted_in_folder,
                    total_cells_counted_in_coord,
                ) = ProcessImage.retrieveDataFromML(
                    Rawimage, MLresults, image_file_name, flat_cell_counted_in_folder
                )
            else:
                (
                    Cell_Data_new,
                    flat_cell_counted_in_folder,
                    total_cells_counted_in_coord,
                ) = ProcessImage.retrieveDataFromML(
                    Rawimage, MLresults, image_file_name, flat_cell_counted_in_folder
                )
                if len(Cell_Data_new) > 0:
                    cell_Data = cell_Data.append(Cell_Data_new)
            total_cells_counted_in_folder += total_cells_counted_in_coord

        if save_excel == True:
            # Save to excel
            cell_Data.to_excel(
                os.path.join(
                    folder,
                    "CellsProperties_{}flat_outof_{}cells.xlsx".format(
                        flat_cell_counted_in_folder, total_cells_counted_in_folder
                    ),
                )
            )

        return cell_Data

    #%%
    def showPlotlyScatter(self, DataFrame, x_axis, y_axis, saving_directory):
        """
        Display the scatters through interactive library Plotly.

        Parameters
        ----------
        DataFrame : pd.dataframe
            The feed in datafram.
        x_axis : str.
            Name of the field as x-axis.
        y_axis : str.
            Name of the field as y-axis.
        saving_directory : str.
            The directory to save the html file.

        Returns
        -------
        None.

        """
        fig = px.scatter(
            DataFrame,
            x=x_axis,
            y=y_axis,
            hover_name=DataFrame.index,
            color="Lib_Tag_contour_ratio",
            hover_data=[
                "Contour_soma_ratio_Lib",
                "Lib_Tag_contour_ratio",
                "ImgNameInfor_Lib",
            ],
            width=1050,
            height=950,
        )
        #        fig.update_layout(hovermode="x")
        fig.write_html(saving_directory, auto_open=True)


if __name__ == "__main__":
    import skimage
    import time
    # from skimage.io import imread
    # =============================================================================

    tag_folder = r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\2020-4-08 Archon citrine library 100FOVs\trial_3_library_cellspicked"
    lib_folder = r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\2020-7-30 Archon1 comparision 100 FOV\code_test"

    tag_round = "Round1"
    lib_round = "Round2"

    # ProcessML = ProcessImageML(WeigthPath = r"C:\MaskRCNN\MaskRCNNGit\MaskRCNN\MaskRCNN\Data\Xin_training_200epoch_2021_1_20\cell20210121T2259\mask_rcnn_cell_0200.h5")
    # ProcessML = ProcessImageML(WeigthPath = r"C:\MaskRCNN\MaskRCNNGit\MaskRCNN\MaskRCNN\Data\Xin_training\cell20210107T1533\mask_rcnn_cell_0050.h5")
    ProcessML = ProcessImageML(
        WeigthPath=r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Martijn\SpikingHek.h5"
    )
    # ProcessML = ProcessImageML()
    # ProcessML.config.WeigthPath = r"C:\MaskRCNN\MaskRCNNGit\MaskRCNN\MaskRCNN\Data\Xin_training\cell20210107T1533\mask_rcnn_cell_0050.h5"
    print(ProcessML.config.WeigthPath)
    # 5.6s for each detection
    img_name = r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\ML images\image segmentation for liposomes\PolyYOLOLiposomeDataset\imgs\2020_06_25_sample1_001_00001.jpg"
    img = skimage.io.imread(img_name)
    for _ in range(5):
        starttime = time.time()
        ProcessML.DetectionOnImage(img, show_result = True)
        endtime = time.time()
        print(endtime-starttime)

    # cell_data = ProcessML.analyze_single_image(img, show_each_cell=True)
    # ProcessML.DetectionOnImage(img, show_result = True)

    # cell_data = ProcessML.analyze_images_in_folder\
    #     (folder=r'M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Delizzia\2021-02-25 Helios WT screening 1000ng 532nm\pos3', generate_zmax = True)
