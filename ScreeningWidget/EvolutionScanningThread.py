# -*- coding: utf-8 -*-
"""
Created on Mon Dec 23 15:10:53 2019

@author: xinmeng
-----------------------------------------------------------Threading class for evolution screening--------------------------------------------------------------------------------
"""
from PyQt5.QtCore import pyqtSignal, QThread
import numpy as np
import time
from PIL import Image
from matplotlib import pyplot as plt
import os
from datetime import datetime
import math
from skimage.io import imread
import skimage.external.tifffile as skimtiff
import threading

from SampleStageControl.stage import LudlStage
from NIDAQ.DAQoperator import DAQmission
from PI_ObjectiveMotor.focuser import PIMotor
from PI_ObjectiveMotor.AutoFocus import FocusFinder
from ThorlabsFilterSlider.filterpyserial import ELL9Filter
from InsightX3.TwoPhotonLaser_backend import InsightX3
from HamamatsuCam.HamamatsuActuator import CamActuator
from ImageAnalysis.ImageProcessing import ProcessImage

# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
class ScanningExecutionThread(QThread):

    ScanningResult = pyqtSignal(
        np.ndarray, np.ndarray, object, object
    )  # The signal for the measurement, we can connect to this signal
    #%%
    def __init__(
        self, RoundQueueDict, RoundCoordsDict, GeneralSettingDict, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.RoundQueueDict = RoundQueueDict
        self.RoundCoordsDict = RoundCoordsDict
        self.GeneralSettingDict = GeneralSettingDict
        self.Status_list = None
        self.ludlStage = LudlStage("COM12")
        self.watchdog_flag = True

        self.clock_source = "DAQ"  # Should be set by GUI.

        self.scansavedirectory = self.GeneralSettingDict["savedirectory"]
        self.meshgridnumber = int(self.GeneralSettingDict["Meshgrid"])

        self.wavelength_offset = (
            0  # An offset of 0.002 mm is observed between 900 and 1280 nm.
        )

    #%%
    def run(self):
        """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #                                                               Connect devices.
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""
        """
        # =============================================================================
        #         connect the Objective motor
        # =============================================================================
        """
        print(
            "----------------------Starting to connect the Objective motor-------------------------"
        )
        self.pi_device_instance = PIMotor()
        print("Objective motor connected.")
        self.errornum = 0
        self.init_focus_position = self.pi_device_instance.pidevice.qPOS(
            self.pi_device_instance.pidevice.axes
        )["1"]
        print("init_focus_position : {}".format(self.init_focus_position))

        """
        # =============================================================================
        #         connect the Hmamatsu camera
        # =============================================================================
        """
        self._use_camera = False
        # Check if camera is used.
        for key in self.RoundQueueDict:
            if "RoundPackage_" in key:
                for waveform_and_cam_key in self.RoundQueueDict[key][1]:
                    if "CameraPackage_" in waveform_and_cam_key:
                        if len(self.RoundQueueDict[key][1][waveform_and_cam_key]) != 0:
                            self._use_camera = True

        if self._use_camera:
            print("Connecting camera...")
            self.HamamatsuCam = CamActuator()
            self.HamamatsuCam.initializeCamera()
        else:
            self.HamamatsuCam = None
            print("No camera involved.")

        """
        # =============================================================================
        #         connect the Insight X3
        # =============================================================================
        """
        if len(self.RoundQueueDict["InsightEvents"]) != 0:
            self.Laserinstance = InsightX3("COM11")
            try:
                # querygap = 1.1
                # self.Laserinstance.SetWatchdogTimer(0) # Disable the laser watchdog!
                #                Status_watchdog_thread = threading.Thread(target = self.Status_watchdog, args=[querygap], daemon=True)
                #                Status_watchdog_thread.start()
                # time.sleep(1)
                # -------------Initialize laser--------------
                self.watchdog_flag = False
                time.sleep(0.5)

                warmupstatus = 0
                while int(warmupstatus) != 100:
                    warmupstatus = self.Laserinstance.QueryWarmupTime()
                    time.sleep(0.6)

                self.watchdog_flag = True
                time.sleep(0.5)
            except:
                print("Laser not connected.")

            # If turn on the laser shutter in the beginning
            if "Shutter_Open" in self.GeneralSettingDict["StartUpEvents"]:
                time.sleep(0.5)

                self.Laserinstance.Open_TunableBeamShutter()

                time.sleep(0.5)
        """
        # =============================================================================
        #         Initialize ML
        # =============================================================================
        """
        self._use_ML = False
        # Check if machine learning segmentation is used.
        for key in self.RoundQueueDict:
            if "RoundPackage_" in key:
                for photocycle_key in self.RoundQueueDict[key][2]:
                    if "PhotocyclePackage_" in photocycle_key:
                        if len(self.RoundQueueDict[key][2][photocycle_key]) != 0:
                            self._use_ML = True
        if self._use_ML:
            from ImageAnalysis.ImageProcessing_MaskRCNN import ProcessImageML

            self.Predictor = ProcessImageML()
            print("ML loaded.")

        #%%
        """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #                                                                  Execution
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""
        GridSequence = 0
        TotalGridNumber = self.meshgridnumber ** 2

        for EachGrid in range(TotalGridNumber):
            """
            #------------------------------------------------------------------------------
            #:::::::::::::::::::::::::::::::: AT EACH GRID ::::::::::::::::::::::::::::::::
            #------------------------------------------------------------------------------
            """
            self.Grid_index = EachGrid
            """
            # =============================================================================
            #         For each small repeat unit in the scanning meshgrid
            # =============================================================================
            """

            time.sleep(0.5)

            for EachRound in range(
                int(len(self.RoundQueueDict) / 2 - 1)
            ):  # EachRound is the round sequence number starting from 0, while the actual number used in dictionary is 1.
                """
                #-------------------------------------------------------------------------------
                #:::::::::::::::::::::::::::::::: AT EACH ROUND ::::::::::::::::::::::::::::::::
                #-------------------------------------------------------------------------------
                """
                print(
                    "----------------------------------------------------------------------------"
                )
                print(
                    "Below is Grid {}, Round {}.".format(EachGrid, EachRound + 1)
                )  # EachRound+1 is the corresponding round number when setting the dictionary starting from round 1.
                """
                # =============================================================================
                #         Execute Insight event at the beginning of each round
                # =============================================================================
                """
                self.laser_init(EachRound)

                """
                # =============================================================================
                #         Execute filter event at the beginning of each round
                # =============================================================================
                """
                self.filters_init(EachRound)

                """
                # =============================================================================
                #         Generate focus position list at the beginning of each round
                # =============================================================================
                """
                if EachRound == 0:
                    ZStackinfor = self.GeneralSettingDict["FocusStackInfoDict"][
                        "RoundPackage_{}".format(EachRound + 1)
                    ]
                    ZStackNum = int(ZStackinfor[ZStackinfor.index("Focus") + 5])
                    ZStackStep = float(
                        ZStackinfor[ZStackinfor.index("Being") + 5 : len(ZStackinfor)]
                    )

                    # Generate position list.
                    ZStacklinspaceStart = (
                        self.init_focus_position
                        - (math.floor(ZStackNum / 2)) * ZStackStep
                    )
                    ZStacklinspaceEnd = (
                        self.init_focus_position
                        + (ZStackNum - math.floor(ZStackNum / 2) - 1) * ZStackStep
                    )

                    self.ZStackPosList = np.linspace(
                        ZStacklinspaceStart, ZStacklinspaceEnd, num=ZStackNum
                    )

                self.currentCoordsSeq = 0
                #%%
                # -------------Unpack infor for stage move.
                CoordsNum = len(
                    self.RoundCoordsDict["CoordsPackage_{}".format(EachRound + 1)]
                )
                for EachCoord in range(CoordsNum):
                    """
                    #------------------------------------------------------------------------------------
                    #:::::::::::::::::::::::::::::::: AT EACH COORDINATE ::::::::::::::::::::::::::::::::
                    #------------------------------------------------------------------------------------
                    """
                    self.error_massage = None

                    self.currentCoordsSeq += 1

                    """
                    # =============================================================================
                    #         Stage movement
                    # =============================================================================
                    """
                    self.coord_array = self.RoundCoordsDict[
                        "CoordsPackage_{}".format(EachRound + 1)
                    ][EachCoord]

                    # Offset coordinate row value for each well.
                    ScanningGridOffset_Row = int(EachGrid % self.meshgridnumber) * (
                        self.GeneralSettingDict["StageGridOffset"]
                    )
                    # Offset coordinate colunm value for each well.
                    ScanningGridOffset_Col = int(EachGrid / self.meshgridnumber) * (
                        self.GeneralSettingDict["StageGridOffset"]
                    )

                    RowIndex = self.coord_array["row"] + ScanningGridOffset_Row
                    ColumnIndex = self.coord_array["col"] + ScanningGridOffset_Col

                    try:
                        # for _ in range(2): # Repeat twice
                        #     self.ludlStage.moveAbs(RowIndex,ColumnIndex) # Row/Column indexs of np.array are opposite of stage row-col indexs.
                        #     time.sleep(1)
                        self.ludlStage.moveAbs(
                            RowIndex, ColumnIndex
                        )  # Row/Column indexs of np.array are opposite of stage row-col indexs.
                        print(
                            "==================Stage move to {}==================".format(
                                [RowIndex, ColumnIndex]
                            )
                        )
                        # Typically it needs 1~ second to move across 15000 stage index.
                        time.sleep(1.8)
                    except:
                        self.error_massage = "Fail_MoveStage"
                        self.errornum += 1
                        print(
                            "Stage move failed! Error number: {}".format(
                                int(self.errornum)
                            )
                        )

                    time.sleep(0.2)

                    """
                    # =============================================================================
                    #                               Focus position
                    #         Unpack the focus stack information, conduct auto-focusing if set.
                    # =============================================================================
                    """
                    # Here also generate the ZStackPosList.
                    self.ZStackNum = self.unpack_focus_stack(
                        EachGrid, EachRound, EachCoord
                    )

                    self.stack_focus_degree_list = []

                    print(
                        "*******************************************Round {}. Current index: {}.**************************************************".format(
                            EachRound + 1, [RowIndex, ColumnIndex]
                        )
                    )

                    # ------------------Move to Z stack focus-------------------
                    for EachZStackPos in range(self.ZStackNum):
                        """
                        #------------------------------------------------------------------------------------
                        #:::::::::::::::::::::::::::::::: AT EACH ZSTACK ::::::::::::::::::::::::::::::::::::
                        #------------------------------------------------------------------------------------
                        """
                        print(
                            "--------------------------------------------Stack {}--------------------------------------------------".format(
                                EachZStackPos + 1
                            )
                        )
                        if self.ZStackNum >= 1:
                            self.ZStackOrder = int(
                                EachZStackPos + 1
                            )  # Here the first one is 1, not starting from 0.

                            self.FocusPos = self.ZStackPosList[
                                EachZStackPos
                            ]  # + self.wavelength_offset

                            # Add the focus degree of previous image to the list.
                            # For stack of 3 only.
                            if EachZStackPos > 0:
                                try:
                                    self.stack_focus_degree_list.append(
                                        self.FocusDegree_img_reconstructed
                                    )

                                except:
                                    # FocusDegree_img_reconstructed is not generated with camera imaging.
                                    pass
                            print(
                                "stack_focus_degree_list is {}".format(
                                    self.stack_focus_degree_list
                                )
                            )
                            # -----Suppose now it's the 3rd stack position-----
                            if len(self.stack_focus_degree_list) == 2:
                                if (
                                    self.stack_focus_degree_list[-1]
                                    < self.stack_focus_degree_list[-2]
                                ):
                                    self.FocusPos = (
                                        self.ZStackPosList[0]
                                        - (
                                            self.ZStackPosList[1]
                                            - self.ZStackPosList[0]
                                        )
                                        / 2
                                    )
                                    print(
                                        "Focus degree decreasing, run the other direction."
                                    )
                            # -------------------------------------------------

                            print("Target focus pos: {}".format(self.FocusPos))

                            self.pi_device_instance.move(self.FocusPos)
                            # self.auto_focus_positionInStack = self.pi_device_instance.pidevice.qPOS(self.pi_device_instance.pidevice.axes)
                            # print("Current position: {:.4f}".format(self.auto_focus_positionInStack['1']))

                            time.sleep(0.3)
                        else:
                            # No Z-stack or auto-focus.
                            self.ZStackOrder = 1
                            self.FocusPos = self.init_focus_position
                        """
                        # =============================================================================
                        #         Execute waveform packages
                        # =============================================================================
                        """
                        self.Waveform_sequence_Num = int(
                            len(
                                self.RoundQueueDict[
                                    "RoundPackage_{}".format(EachRound + 1)
                                ][0]
                            )
                        )
                        # ------------For waveforms in each coordinate----------
                        for EachWaveform in range(self.Waveform_sequence_Num):

                            """
                            # =============================================================================
                            #         For photo-cycle
                            # =============================================================================
                            """
                            # Get the photo cycle information
                            PhotocyclePackageToBeExecute = self.RoundQueueDict[
                                "RoundPackage_{}".format(EachRound + 1)
                            ][2]["PhotocyclePackage_{}".format(EachWaveform + 1)]

                            # See if in this waveform sequence photo cycle is involved.
                            # PhotocyclePackageToBeExecute is {} if not configured.
                            if len(PhotocyclePackageToBeExecute) > 0:

                                # Load the previous acquired camera image
                                self.cam_tif_name = r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Octoscope\2020-8-13 Screening Archon1 library V5 and 6\V6\Round2_Coords181_R19800C0_PMT_0Zmax.tif"
                                previous_cam_img = imread(self.cam_tif_name)
                                img_width = previous_cam_img.shape[1]

                                img_height = previous_cam_img.shape[0]

                                # Get the segmentation of full image.
                                fig, ax = plt.subplots()
                                MLresults = self.Predictor.DetectionOnImage(
                                    previous_cam_img, axis=ax
                                )

                                ROI_number = len(MLresults["scores"])
                                print("roi number: {}".format(ROI_number))
                                for each_ROI in range(ROI_number):
                                    # if MLresults['class_ids'][each_ROI] == 3:
                                    ROIlist = MLresults["rois"][each_ROI]
                                    print(ROIlist)
                                    # np array's column([1]) is the width of image, and is the row in stage coordinates.
                                    ROI_center_width = int(
                                        ROIlist[1] + (ROIlist[3] - ROIlist[1]) / 2
                                    )
                                    print("ROI_center_width ".format(ROIlist))
                                    ROI_center_height = int(
                                        ROIlist[0] + (ROIlist[2] + ROIlist[0]) / 2
                                    )
                                    print("ROI_center_height ".format(ROIlist))
                                    cam_stage_transform_factor = 1.135

                                    stage_move_col = (
                                        int((img_width) / 2) - ROI_center_width
                                    ) * cam_stage_transform_factor
                                    print(stage_move_col)
                                    stage_move_row = (
                                        int((img_height) / 2) - ROI_center_height
                                    ) * cam_stage_transform_factor
                                    print(stage_move_row)
                                    # Move cell of interest to the center of field of view
                                    self.ludlStage.moveRel(
                                        xRel=stage_move_row, yRel=stage_move_col
                                    )

                                    time.sleep(1)

                                    # Move the cell back
                                    self.ludlStage.moveRel(
                                        xRel=-1 * stage_move_row,
                                        yRel=-1 * stage_move_col,
                                    )
                                    time.sleep(1)
                            # --------------------------------------------------

                            """
                            # =============================================================================
                            #         Execute pre-set operations at EACH COORDINATE.
                            # =============================================================================
                            """
                            self.inidividual_coordinate_operation(
                                EachRound, EachWaveform, RowIndex, ColumnIndex
                            )

                        time.sleep(0.6)  # Wait for receiving data to be done.
                    time.sleep(0.5)
                    print(
                        "*************************************************************************************************************************"
                    )

        #%%
        """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #                                                            Disconnect devices.
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

        # Switch off laser
        if len(self.RoundQueueDict["InsightEvents"]) != 0:
            self.watchdog_flag = False
            time.sleep(0.5)

            self.Laserinstance.Close_TunableBeamShutter()

            time.sleep(0.5)

            self.Laserinstance.SaveVariables()

            self.Laserinstance.Turn_Off_PumpLaser()

        # Disconnect camera
        if self._use_camera == True:
            self.HamamatsuCam.Exit()

        # Disconnect focus motor
        try:
            self.pi_device_instance.CloseMotorConnection()
            print("Objective motor disconnected.")
        except:
            pass

    #%%
    def laser_init(self, EachRound):
        """
        Execute Insight event at the beginning of each round

        Parameters
        ----------
        EachRound : int
            Round index.

        Returns
        -------
        None.

        """
        # -Unpack infor for Insight X3. In the list, the first one is for shutter event and the second one is for wavelength event.
        InsightX3EventIndexList = [
            i
            for i, x in enumerate(self.RoundQueueDict["InsightEvents"])
            if "Round_{}".format(EachRound + 1) in x
        ]

        if len(InsightX3EventIndexList) == 1:
            print(InsightX3EventIndexList)
            InsightText = self.RoundQueueDict["InsightEvents"][
                InsightX3EventIndexList[0]
            ]
            if "Shutter_Open" in InsightText:
                self.watchdog_flag = False
                time.sleep(0.5)

                self.Laserinstance.Open_TunableBeamShutter()

                time.sleep(0.5)
                print("Laser shutter open.")
                self.watchdog_flag = True
                time.sleep(0.5)

            elif "Shutter_Close" in InsightText:
                self.watchdog_flag = False
                time.sleep(0.5)

                self.Laserinstance.Close_TunableBeamShutter()

                time.sleep(0.5)
                print("Laser shutter closed.")
                self.watchdog_flag = True
                time.sleep(0.5)
            elif "WavelengthTo" in InsightText:
                self.watchdog_flag = False
                time.sleep(0.5)
                TargetWavelen = int(
                    InsightText[InsightText.index("To_") + 3 : len(InsightText)]
                )

                if TargetWavelen == 1280:
                    self.wavelength_offset = (
                        -0.002
                    )  # give an offset if wavelength goes to 1280.
                elif TargetWavelen == 900:
                    self.wavelength_offset = 0

                self.Laserinstance.SetWavelength(TargetWavelen)

                time.sleep(5)
                self.watchdog_flag = True
                time.sleep(0.5)

        elif len(InsightX3EventIndexList) == 2:

            InsightText_wl = self.RoundQueueDict["InsightEvents"][
                InsightX3EventIndexList[1]
            ]
            InsightText_st = self.RoundQueueDict["InsightEvents"][
                InsightX3EventIndexList[0]
            ]

            if "WavelengthTo" in InsightText_wl and "Shutter_Open" in InsightText_st:
                self.watchdog_flag = False
                time.sleep(0.5)
                TargetWavelen = int(
                    InsightText_wl[
                        InsightText_wl.index("To_") + 3 : len(InsightText_wl)
                    ]
                )

                self.Laserinstance.SetWavelength(TargetWavelen)

                if TargetWavelen == 1280:
                    self.wavelength_offset = (
                        -0.002
                    )  # give an offset if wavelength goes to 1280.
                elif TargetWavelen == 900:
                    self.wavelength_offset = 0

                time.sleep(5)

                self.Laserinstance.Open_TunableBeamShutter()

                print("Laser shutter open.")
                self.watchdog_flag = True
                time.sleep(0.5)

            elif "WavelengthTo" in InsightText_wl and "Shutter_Close" in InsightText_st:
                self.watchdog_flag = False
                time.sleep(0.5)
                TargetWavelen = int(
                    InsightText_wl[
                        InsightText_wl.index("To_") + 3 : len(InsightText_wl)
                    ]
                )

                self.Laserinstance.SetWavelength(TargetWavelen)

                if TargetWavelen == 1280:
                    self.wavelength_offset = (
                        -0.002
                    )  # give an offset if wavelength goes to 1280.
                elif TargetWavelen == 900:
                    self.wavelength_offset = 0

                time.sleep(5)

                self.Laserinstance.Close_TunableBeamShutter()

                time.sleep(1)
                print("Laser shutter closed.")
                self.watchdog_flag = True
                time.sleep(0.5)

            time.sleep(2)

    def filters_init(self, EachRound):
        """
        Execute filter event at the beginning of each round.

        Parameters
        ----------
        EachRound : int
            Round index.

        Returns
        -------
        None.

        """

        # -Unpack infor for filter event. In the list, the first one is for ND filter and the second one is for emission filter.
        FilterEventIndexList = [
            i
            for i, x in enumerate(self.RoundQueueDict["FilterEvents"])
            if "Round_{}".format(EachRound + 1) in x
        ]

        if len(FilterEventIndexList) > 0:
            NDposText = self.RoundQueueDict["FilterEvents"][FilterEventIndexList[0]]
            NDnumber = NDposText[NDposText.index("ToPos_") + 6 : len(NDposText)]

            EMposText = self.RoundQueueDict["FilterEvents"][FilterEventIndexList[1]]
            EMprotein = EMposText[EMposText.index("ToPos_") + 6 : len(EMposText)]

            # "COM9" for filter 1 port, which has ND values from 0 to 3.
            # "COM7" for filter 2 port, which has ND values from 0 to 0.5.
            if NDnumber == "0":
                ND_filter1_Pos = 0
                ND_filter2_Pos = 0
            elif NDnumber == "0.1":
                ND_filter1_Pos = 0
                ND_filter2_Pos = 1
            elif NDnumber == "0.3":
                ND_filter1_Pos = 0
                ND_filter2_Pos = 2
            elif NDnumber == "0.5":
                ND_filter1_Pos = 0
                ND_filter2_Pos = 3
            elif NDnumber == "1":
                ND_filter1_Pos = 1
                ND_filter2_Pos = 0
            elif NDnumber == "1.1":
                ND_filter1_Pos = 1
                ND_filter2_Pos = 1
            elif NDnumber == "1.3":
                ND_filter1_Pos = 1
                ND_filter2_Pos = 2
            elif NDnumber == "1.5":
                ND_filter1_Pos = 1
                ND_filter2_Pos = 3
            elif NDnumber == "2":
                ND_filter1_Pos = 2
                ND_filter2_Pos = 0
            elif NDnumber == "2.3":
                ND_filter1_Pos = 2
                ND_filter2_Pos = 2
            elif NDnumber == "2.5":
                ND_filter1_Pos = 2
                ND_filter2_Pos = 3
            elif NDnumber == "3":
                ND_filter1_Pos = 3
                ND_filter2_Pos = 0

            if EMprotein == "Arch":
                EM_filter_Pos = 0
            elif EMprotein == "eGFP" or EMprotein == "Citrine":
                EM_filter_Pos = 1

            # Execution
            if ND_filter1_Pos != None and ND_filter2_Pos != None:
                # Move filter 1
                self.filter1 = ELL9Filter("COM9")
                self.filter1.moveToPosition(ND_filter1_Pos)
                time.sleep(1)
                # Move filter 2
                self.filter2 = ELL9Filter("COM7")
                self.filter2.moveToPosition(ND_filter2_Pos)
                time.sleep(1)
            if EM_filter_Pos != None:
                self.filter3 = ELL9Filter("COM15")
                self.filter3.moveToPosition(EM_filter_Pos)
                time.sleep(1)

    def unpack_focus_stack(self, EachGrid, EachRound, EachCoord):
        """
        Unpack the focus stack information.
        Determine focus position either from pre-set numbers of by auto-focusing.

        Parameters
        ----------
        EachGrid : int
            Current grid index.
        EachRound : int
            Current round index.
        EachCoord : int
            Current coordinate index.

        Returns
        -------
        ZStackNum : int
            Number of focus positions in stack.
        ZStackPosList : list
            List of focus stack positions for objective to go to.

        """
        ZStackinfor = self.GeneralSettingDict["FocusStackInfoDict"][
            "RoundPackage_{}".format(EachRound + 1)
        ]
        ZStackNum = int(ZStackinfor[ZStackinfor.index("Focus") + 5])
        ZStackStep = float(
            ZStackinfor[ZStackinfor.index("Being") + 5 : len(ZStackinfor)]
        )

        try:
            AutoFocusConfig = self.GeneralSettingDict["AutoFocusConfig"]
        except:
            pass

        # If manual focus correction applies, unpact the target focus infor.
        if len(self.GeneralSettingDict["FocusCorrectionMatrixDict"]) > 0:
            FocusPosArray = self.GeneralSettingDict["FocusCorrectionMatrixDict"][
                "RoundPackage_{}_Grid_{}".format(EachRound + 1, EachGrid)
            ]
            FocusPosArray = FocusPosArray.flatten("F")
            FocusPos_fromCorrection = FocusPosArray[EachCoord]

            ZStacklinspaceStart = (
                FocusPos_fromCorrection - (math.floor(ZStackNum / 2)) * ZStackStep
            )
            ZStacklinspaceEnd = (
                FocusPos_fromCorrection
                + (ZStackNum - math.floor(ZStackNum / 2) - 1) * ZStackStep
            )

        # With auto-focus correction
        else:
            # If go for auto-focus at this coordinate
            auto_focus_flag = self.coord_array["auto_focus_flag"]
            # auto_focus_flag = False
            print("focus_position {}".format(self.coord_array["focus_position"]))

            # -----------------------Auto focus---------------------------------
            if auto_focus_flag == "yes":

                if self.coord_array["focus_position"] == -1.0:
                    instance_FocusFinder = FocusFinder(
                        source_of_image=AutoFocusConfig["source_of_image"],
                        init_search_range=AutoFocusConfig["init_search_range"],
                        total_step_number=AutoFocusConfig["total_step_number"],
                        imaging_conditions=AutoFocusConfig["imaging_conditions"],
                        motor_handle=self.pi_device_instance,
                        camera_handle=self.HamamatsuCam,
                    )
                    print("--------------Start auto-focusing-----------------")
                    if self.HamamatsuCam != None:
                        # For camera AF
                        self.auto_focus_position = instance_FocusFinder.gaussian_fit()
                    else:
                        # For PMT AF
                        self.auto_focus_position = instance_FocusFinder.bisection()

                    relative_move_coords = [[1550, 0], [0, 1550], [1550, 1550]]
                    trial_num = 0
                    while (
                        self.auto_focus_position == False
                    ):  # If there's no cell in FOV
                        if trial_num <= 2:
                            print("No cells found. move to next pos.")
                            # Move to next position in real scanning coordinates.
                            self.ludlStage.moveRel(
                                relative_move_coords[trial_num][0],
                                relative_move_coords[trial_num][1],
                            )
                            time.sleep(1)
                            print("Now stage pos is {}".format(self.ludlStage.getPos()))

                            if self.HamamatsuCam != None:
                                # For camera AF
                                self.auto_focus_position = (
                                    instance_FocusFinder.gaussian_fit()
                                )
                            else:
                                # For PMT AF
                                self.auto_focus_position = (
                                    instance_FocusFinder.bisection()
                                )
                            # Move back
                            self.ludlStage.moveRel(
                                -1 * relative_move_coords[trial_num][0],
                                -1 * relative_move_coords[trial_num][1],
                            )

                            trial_num += 1
                        else:
                            print("No cells in neighbouring area.")
                            self.auto_focus_position = self.ZStackPosList[
                                int(len(self.ZStackPosList) / 2)
                            ]
                            break

                    print("--------------End of auto-focusing----------------")
                    time.sleep(1)

                    # Record the position, try to write it in the NEXT round dict.
                    try:
                        AF_coord_row = self.RoundCoordsDict[
                            "CoordsPackage_{}".format(EachRound + 1)
                        ][EachCoord]["row"]
                        AF_coord_col = self.RoundCoordsDict[
                            "CoordsPackage_{}".format(EachRound + 1)
                        ][EachCoord]["col"]

                        # Loop through next round coordinates, find one with same row and col.
                        for coordinate in self.RoundCoordsDict[
                            "CoordsPackage_{}".format(EachRound + 2)
                        ]:
                            if (
                                coordinate["row"] == AF_coord_row
                                and coordinate["col"] == AF_coord_col
                            ):
                                coordinate["focus_position"] = self.auto_focus_position
                                print(
                                    "Write founded focus position to next round coord: {}.".format(
                                        coordinate
                                    )
                                )
                        # self.RoundCoordsDict['CoordsPackage_{}'.format(EachRound + 2)][EachCoord]['focus_position'] = self.auto_focus_position
                    except:  # If it's already the last round, skip.
                        pass

                    # Generate position list.
                    ZStacklinspaceStart = (
                        self.auto_focus_position
                        - (math.floor(ZStackNum / 2)) * ZStackStep
                    )
                    ZStacklinspaceEnd = (
                        self.auto_focus_position
                        + (ZStackNum - math.floor(ZStackNum / 2) - 1) * ZStackStep
                    )

                else:  # If there's already position from last round, move to it.

                    # EachRound+1 is current round number.
                    self.previous_auto_focus_position = self.RoundCoordsDict[
                        "CoordsPackage_{}".format(EachRound + 1)
                    ][EachCoord]["focus_position"]
                    print(
                        "Previous_auto_focus_position found: {}".format(
                            self.previous_auto_focus_position
                        )
                    )
                    # =================Pass on auto-focus positions to coming rounds.================
                    # try:
                    #     # Record the position, try to write it in the NEXT round dict.
                    #     self.RoundCoordsDict['CoordsPackage_{}'.format(EachRound + 2)][EachCoord]['focus_position'] = self.previous_auto_focus_position
                    # except:
                    #     pass

                    # Generate position list.
                    ZStacklinspaceStart = (
                        self.previous_auto_focus_position
                        - (math.floor(ZStackNum / 2)) * ZStackStep
                    )
                    ZStacklinspaceEnd = (
                        self.previous_auto_focus_position
                        + (ZStackNum - math.floor(ZStackNum / 2) - 1) * ZStackStep
                    )

                    # self.previous_auto_focus_position = self.auto_focus_position
                    # print("=====================Move to last recorded position=================")
                    # self.pi_device_instance.move(self.previous_auto_focus_position)
                    # time.sleep(0.2)

                    # instance_FocusFinder = FocusFinder(motor_handle = self.pi_device_instance)
                    # print("--------------Start auto-focusing-----------------")
                    # self.auto_focus_position = instance_FocusFinder.bisection()

                    # try:
                    #     if self.auto_focus_position[0] == False: # If there's no cell in FOV
                    #     # Skip?  mid_position = [False, self.current_pos]
                    #         self.auto_focus_position = self.auto_focus_position[1]
                    # except:
                    #     pass

                    # print("--------------End of auto-focusing----------------")
                    # time.sleep(1)

                    # # Record the position, try to write it in the NEXT round dict.
                    # try:
                    #     self.RoundCoordsDict['CoordsPackage_{}'.format(EachRound + 2)][EachCoord]['focus_position'] = self.auto_focus_position
                    # except:# If it's already the last round, skip.
                    #     pass

                # Generate the position list, for none-auto-focus coordinates they will use the same list variable.
                self.ZStackPosList = np.linspace(
                    ZStacklinspaceStart, ZStacklinspaceEnd, num=ZStackNum
                )
                print("ZStackPos is : {}".format(self.ZStackPosList))
            # ------------------------------------------------------------------
            # If not auto focus, use the same list variable self.ZStackPosList.
            elif auto_focus_flag == "no":
                pass
            # ------------------------------------------------------------------
            # If it's auto-focus round, skip next waveforms.
            elif auto_focus_flag == "pure AF":
                print("--------------Finding focus-----------------")

                instance_FocusFinder = FocusFinder(
                    source_of_image=AutoFocusConfig["source_of_image"],
                    init_search_range=AutoFocusConfig["init_search_range"],
                    total_step_number=AutoFocusConfig["total_step_number"],
                    imaging_conditions=AutoFocusConfig["imaging_conditions"],
                    motor_handle=self.pi_device_instance,
                    camera_handle=self.HamamatsuCam,
                )
                print("--------------Start auto-focusing-----------------")
                if self.HamamatsuCam != None:
                    # For camera AF
                    self.auto_focus_position = instance_FocusFinder.gaussian_fit()
                else:
                    # For PMT AF
                    self.auto_focus_position = instance_FocusFinder.bisection()

                relative_move_coords = [[1550, 0], [0, 1550], [1550, 1550]]
                trial_num = 0
                while self.auto_focus_position == False:  # If there's no cell in FOV
                    if trial_num <= 2:
                        print("No cells found. move to next pos.")
                        # Move to next position in real scanning coordinates.
                        self.ludlStage.moveRel(
                            relative_move_coords[trial_num][0],
                            relative_move_coords[trial_num][1],
                        )
                        time.sleep(1)
                        print("Now stage pos is {}".format(self.ludlStage.getPos()))

                        if self.HamamatsuCam != None:
                            # For camera AF
                            self.auto_focus_position = (
                                instance_FocusFinder.gaussian_fit()
                            )
                        else:
                            # For PMT AF
                            self.auto_focus_position = instance_FocusFinder.bisection()

                        # Move back
                        self.ludlStage.moveRel(
                            -1 * relative_move_coords[trial_num][0],
                            -1 * relative_move_coords[trial_num][1],
                        )

                        trial_num += 1
                    else:
                        print(
                            "No cells in neighbouring area. Write init_focus_position."
                        )
                        try:
                            self.auto_focus_position = self.ZStackPosList[
                                int(len(self.ZStackPosList) / 2)
                            ]
                        except:
                            self.auto_focus_position = self.init_focus_position
                        break

                print("--------------End of auto-focusing----------------")
                time.sleep(1)

                # Record the position, try to write it in the NEXT round dict.
                try:
                    AF_coord_row = self.RoundCoordsDict[
                        "CoordsPackage_{}".format(EachRound + 1)
                    ][EachCoord]["row"]
                    AF_coord_col = self.RoundCoordsDict[
                        "CoordsPackage_{}".format(EachRound + 1)
                    ][EachCoord]["col"]

                    # Loop through next round coordinates, find one with same row and col.
                    for coordinate in self.RoundCoordsDict[
                        "CoordsPackage_{}".format(EachRound + 2)
                    ]:
                        if (
                            coordinate["row"] == AF_coord_row
                            and coordinate["col"] == AF_coord_col
                        ):
                            coordinate["focus_position"] = self.auto_focus_position

                            print(
                                "Write founded focus position to next round coord: {}.".format(
                                    coordinate
                                )
                            )

                except:  # If it's already the last round, skip.
                    pass

                # Make sure it skip waveform execution
                ZStackNum = 0

        return ZStackNum

    def inidividual_coordinate_operation(
        self, EachRound, EachWaveform, RowIndex, ColumnIndex
    ):
        """
        Execute pre-set operations at each coordinate.

        Parameters
        ----------
        EachRound : int
            Current round index.
        EachWaveform : int
            Current waveform package index.
        RowIndex : int
            Current sample stage row index.
        ColumnIndex : int
            Current sample stage row index.

        Returns
        -------
        None.

        """
        # Extract information
        WaveformPackageToBeExecute = self.RoundQueueDict[
            "RoundPackage_{}".format(EachRound + 1)
        ][0]["WaveformPackage_{}".format(EachWaveform + 1)]
        CameraPackageToBeExecute = self.RoundQueueDict[
            "RoundPackage_{}".format(EachRound + 1)
        ][1]["CameraPackage_{}".format(EachWaveform + 1)]
        WaveformPackageGalvoInfor = self.RoundQueueDict[
            "GalvoInforPackage_{}".format(EachRound + 1)
        ]["GalvoInfor_{}".format(EachWaveform + 1)]

        self.readinchan = WaveformPackageToBeExecute[3]
        self.RoundWaveformIndex = [
            EachRound + 1,
            EachWaveform + 1,
        ]  # first is current round number, second is current waveform package number.
        self.CurrentPosIndex = [RowIndex, ColumnIndex]

        # ----------------Camera operations-----------------
        _camera_isUsed = False
        if CameraPackageToBeExecute != {}:  # if camera operations are configured
            _camera_isUsed = True
            CamSettigList = CameraPackageToBeExecute["Settings"]
            self.HamamatsuCam.StartStreaming(
                BufferNumber=CameraPackageToBeExecute["Buffer_number"],
                trigger_source=CamSettigList[CamSettigList.index("trigger_source") + 1],
                exposure_time=CamSettigList[CamSettigList.index("exposure_time") + 1],
                trigger_active=CamSettigList[CamSettigList.index("trigger_active") + 1],
                subarray_hsize=CamSettigList[CamSettigList.index("subarray_hsize") + 1],
                subarray_vsize=CamSettigList[CamSettigList.index("subarray_vsize") + 1],
                subarray_hpos=CamSettigList[CamSettigList.index("subarray_hpos") + 1],
                subarray_vpos=CamSettigList[CamSettigList.index("subarray_vpos") + 1],
            )
            # HamamatsuCam starts another thread to pull out frames from buffer.
            # Make sure that the camera is prepared before waveform execution.
            #                                while self.HamamatsuCam.isStreaming == False:
            #                                    print('Waiting for camera...')
            #                                    time.sleep(0.5)
            time.sleep(1)
        print("Now start waveforms")
        # ----------------Waveforms operations--------------
        if (
            WaveformPackageGalvoInfor != "NoGalvo"
        ):  # Unpack the information of galvo scanning.
            self.readinchan = WaveformPackageGalvoInfor[0]
            self.repeatnum = WaveformPackageGalvoInfor[1]
            self.PMT_data_index_array = WaveformPackageGalvoInfor[2]
            self.averagenum = WaveformPackageGalvoInfor[3]
            self.lenSample_1 = WaveformPackageGalvoInfor[4]
            self.ScanArrayXnum = WaveformPackageGalvoInfor[5]

        self.adcollector = DAQmission()
        # self.adcollector.collected_data.connect(self.ProcessData)
        self.adcollector.runWaveforms(
            clock_source=self.clock_source,
            sampling_rate=WaveformPackageToBeExecute[0],
            analog_signals=WaveformPackageToBeExecute[1],
            digital_signals=WaveformPackageToBeExecute[2],
            readin_channels=WaveformPackageToBeExecute[3],
        )
        self.adcollector.save_as_binary(self.scansavedirectory)
        self.recorded_raw_data = self.adcollector.get_raw_data()
        self.Process_raw_data()

        # ------------------Camera saving-------------------
        if _camera_isUsed == True:
            self.HamamatsuCam.isSaving = True
            img_text = (
                "_Cam_"
                + str(self.RoundWaveformIndex[1])
                + "_Zpos"
                + str(self.ZStackOrder)
            )
            self.cam_tif_name = self.generate_tif_name(extra_text=img_text)
            self.HamamatsuCam.StopStreaming(saving_dir=self.cam_tif_name)
            # Make sure that the saving process is finished.
            while self.HamamatsuCam.isSaving == True:
                print("Camera saving...")
                time.sleep(0.5)
            time.sleep(1)

        time.sleep(0.5)

    def Process_raw_data(self):

        self.channel_number = len(self.recorded_raw_data)

        self.data_collected_0 = (
            self.recorded_raw_data[0][0 : len(self.recorded_raw_data[0]) - 1] * -1
        )
        print(len(self.data_collected_0))

        if self.channel_number == 1:
            if "Vp" in self.readinchan:
                pass
            elif "Ip" in self.readinchan:
                pass
            elif (
                "PMT" in self.readinchan
            ):  # repeatnum, PMT_data_index_array, averagenum, ScanArrayXnum
                # Reconstruct the image from np array and save it.
                self.PMT_image_processing()

        elif self.channel_number == 2:
            if "PMT" not in self.readinchan:
                pass
            elif "PMT" in self.readinchan:

                self.PMT_image_processing()

        print("ProcessData executed.")

    # def ProcessData(self, data_waveformreceived):
    #     print('ZStackOrder is:'+str(self.ZStackOrder)+'numis_'+str(self.ZStackNum))
    #     self.adcollector.save_as_binary(self.scansavedirectory)

    #     self.channel_number = len(data_waveformreceived)

    #     self.data_collected_0 = data_waveformreceived[0]*-1
    #     self.data_collected_0 = self.data_collected_0[0:len(self.data_collected_0)-1]
    #     print(len(self.data_collected_0))

    #     if self.channel_number == 1:
    #         if 'Vp' in self.readinchan:
    #             pass
    #         elif 'Ip' in self.readinchan:
    #             pass
    #         elif 'PMT' in self.readinchan:  # repeatnum, PMT_data_index_array, averagenum, ScanArrayXnum

    #             # Reconstruct the image from np array and save it.
    #             self.PMT_image_processing()

    #     elif self.channel_number == 2:
    #         if 'PMT' not in self.readinchan:
    #             pass
    #         elif 'PMT' in self.readinchan:

    #             self.PMT_image_processing()

    #     print('ProcessData executed.')

    def PMT_image_processing(self):
        """
        Reconstruct the image from np array and save it.

        Returns
        -------
        None.

        """
        for imageSequence in range(self.repeatnum):

            try:
                self.PMT_image_reconstructed_array = self.data_collected_0[
                    np.where(self.PMT_data_index_array == imageSequence + 1)
                ]

                Dataholder_average = np.mean(
                    self.PMT_image_reconstructed_array.reshape(self.averagenum, -1),
                    axis=0,
                )

                Value_yPixels = int(self.lenSample_1 / self.ScanArrayXnum)
                self.PMT_image_reconstructed = np.reshape(
                    Dataholder_average, (Value_yPixels, self.ScanArrayXnum)
                )

                self.PMT_image_reconstructed = self.PMT_image_reconstructed[
                    :, 50:550
                ]  # Crop size based on: M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\Data\Xin\2019-12-30 2p beads area test 4um
                # self.PMT_image_reconstructed = self.PMT_image_reconstructed[:, 70:326] # for 256*256 images

                # Evaluate the focus degree of re-constructed image.
                self.FocusDegree_img_reconstructed = ProcessImage.local_entropy(
                    self.PMT_image_reconstructed.astype("float32")
                )
                print(
                    "FocusDegree_img_reconstructed is {}".format(
                        self.FocusDegree_img_reconstructed
                    )
                )

                # Save the individual file.
                with skimtiff.TiffWriter(
                    os.path.join(
                        self.scansavedirectory,
                        "Round"
                        + str(self.RoundWaveformIndex[0])
                        + "_Grid"
                        + str(self.Grid_index)
                        + "_Coords"
                        + str(self.currentCoordsSeq)
                        + "_R"
                        + str(self.CurrentPosIndex[0])
                        + "C"
                        + str(self.CurrentPosIndex[1])
                        + "_PMT_"
                        + str(imageSequence)
                        + "Zpos"
                        + str(self.ZStackOrder)
                        + ".tif",
                    ),
                    imagej=True,
                ) as tif:
                    tif.save(
                        self.PMT_image_reconstructed.astype("float32"),
                        compress=0,
                        metadata={"FocusPos: ": str(self.FocusPos)},
                    )

                plt.figure()
                plt.imshow(
                    self.PMT_image_reconstructed, cmap=plt.cm.gray
                )  # For reconstructed image we pull out the first layer, getting 2d img.
                plt.show()

                # ---------------------------------------------For multiple images in one z pos, Stack the arrays into a 3d array--------------------------------------------------------------------------
                # if imageSequence == 0:
                #     self.PMT_image_reconstructed_stack = self.PMT_image_reconstructed[np.newaxis, :, :] # Turns into 3d array
                # else:
                #     self.PMT_image_reconstructed_stack = np.concatenate((self.PMT_image_reconstructed_stack, self.PMT_image_reconstructed[np.newaxis, :, :]), axis=0)
                #     print(self.PMT_image_reconstructed_stack.shape)

                # ---------------------------------------------Calculate the z max projection-----------------------------------------------------------------------
                if self.repeatnum == 1:  # Consider one repeat image situlation
                    if self.ZStackNum > 1:
                        if self.ZStackOrder == 1:
                            self.PMT_image_maxprojection_stack = (
                                self.PMT_image_reconstructed[np.newaxis, :, :]
                            )

                        else:

                            self.PMT_image_maxprojection_stack = np.concatenate(
                                (
                                    self.PMT_image_maxprojection_stack,
                                    self.PMT_image_reconstructed[np.newaxis, :, :],
                                ),
                                axis=0,
                            )

                    else:
                        self.PMT_image_maxprojection_stack = (
                            self.PMT_image_reconstructed[np.newaxis, :, :]
                        )

                # Save the max projection image
                if self.ZStackOrder == self.ZStackNum:
                    self.PMT_image_maxprojection = np.max(
                        self.PMT_image_maxprojection_stack, axis=0
                    )

                    # Save the zmax file.
                    with skimtiff.TiffWriter(
                        os.path.join(
                            self.scansavedirectory,
                            "Round"
                            + str(self.RoundWaveformIndex[0])
                            + "_Grid"
                            + str(self.Grid_index)
                            + "_Coords"
                            + str(self.currentCoordsSeq)
                            + "_R"
                            + str(self.CurrentPosIndex[0])
                            + "C"
                            + str(self.CurrentPosIndex[1])
                            + "_PMT_"
                            + str(imageSequence)
                            + "Zmax"
                            + ".tif",
                        ),
                        imagej=True,
                    ) as tif:
                        tif.save(
                            self.PMT_image_maxprojection.astype("float32"),
                            compress=0,
                            metadata={"FocusPos: ": str(self.FocusPos)},
                        )

            except:
                print("No.{} image failed to generate.".format(imageSequence))

    def generate_tif_name(self, extra_text="_"):

        tif_name = os.path.join(
            self.scansavedirectory,
            "Round"
            + str(self.RoundWaveformIndex[0])
            + "_Coords"
            + str(self.currentCoordsSeq)
            + "_R"
            + str(self.CurrentPosIndex[0])
            + "C"
            + str(self.CurrentPosIndex[1])
            + extra_text
            + ".tif",
        )
        return tif_name

    # ----------------------------------------------------------------WatchDog for laser----------------------------------------------------------------------------------
    def Status_watchdog(self, querygap):

        while True:
            if self.watchdog_flag == True:
                self.Status_list = self.Laserinstance.QueryStatus()
                time.sleep(querygap)
            else:
                print("Watchdog stopped")
                time.sleep(querygap)


if __name__ == "__main__":

    def generate_tif_name(extra_text="_"):

        tif_name = os.path.join(
            r"M:\tnw\ist\do\projects\Neurophotonics\Brinkslab\People\Xin Meng\Code",
            "Round"
            + str(1)
            + "_Coords"
            + str(12)
            + "_R"
            + str(11)
            + "C"
            + str(22)
            + extra_text
            + ".tif",
        )
        return tif_name

    name = generate_tif_name(extra_text="img_text")
    print(name)
