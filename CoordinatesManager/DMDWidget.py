#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul  7 10:44:31 2020

@author: Izak de Heer

-------------------------------------------------------------------------------
3/8/2020-Xin
'Settings' control panel added.
    Normally DMD projecting with dark phase of minimum 44 us in between switching
    of frames in sequence, set ALP_BIN_MODE to ALP_BIN_UNINTERRUPTED to project
    only one still image to avoid noise introduced by dark phase.
    
Adding 'laser' to CoordinateWidget2 signal list.
"""
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (
    QWidget,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QGroupBox,
    QTabWidget,
    QGraphicsView,
    QGraphicsScene,
    QListWidget,
    QSizePolicy,
    QLabel,
    QComboBox,
    QLayout,
    QStackedWidget,
    QSpinBox,
    QLineEdit,
)

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5 import QtGui


from CoordinatesManager import DMDActuator, Registrator, CoordinateTransformations
from ImageAnalysis.ImageProcessing import ProcessImage

import sys

sys.path.append("../")
import os
from StylishQT import MySwitch, roundQGroupBox, SquareImageView
import matplotlib.pyplot as plt
from skimage.color import rgb2gray
import numpy as np


class DMDWidget(QWidget):

    sig_request_mask_coordinates = pyqtSignal()
    sig_start_registration = pyqtSignal()
    sig_finished_registration = pyqtSignal()

    def __init__(self, parent=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.main_application = parent

        self.set_transformation_saving_location(
            os.getcwd() + "/CoordinatesManager/Registration/dmd_transformation"
        )

        self.init_gui()

    def init_gui(self):
        layout = QGridLayout()

        self.setFixedSize(320, 400)

        self.box = roundQGroupBox()
        self.box.setTitle("DMD control")
        box_layout = QGridLayout()
        self.box.setLayout(box_layout)

        self.setLayout(layout)

        self.connect_button = QPushButton("Connect")
        self.connect_button.setStyleSheet("QPushButton {background-color: #A3C1DA;}")
        self.register_button = QPushButton("Register")

        lasers = ["640", "532", "488"]
        self.transform_for_laser_menu = QListWidget()
        self.transform_for_laser_menu.addItems(lasers)
        self.transform_for_laser_menu.setFixedHeight(52)
        self.transform_for_laser_menu.setFixedWidth(82)
        self.transform_for_laser_menu.setCurrentRow(0)
        self.project_button = QPushButton("Start projecting")
        self.project_button.setStyleSheet("QPushButton {background-color: #99FFCC;}")
        self.clear_button = QPushButton("Clear memory")
        self.white_project_button = QPushButton("Full illum.")
        self.white_project_button.setStyleSheet(
            "QPushButton {background-color: #FFE5CC;}"
        )
        self.load_mask_container_stack = QStackedWidget()

        self.connect_button.clicked.connect(self.connect)
        self.register_button.clicked.connect(
            lambda: self.register(
                self.transform_for_laser_menu.selectedItems()[0].text()
            )
        )
        self.project_button.clicked.connect(self.project)
        self.clear_button.clicked.connect(self.clear)
        self.white_project_button.clicked.connect(self.project_full_white)

        # Stack page 1
        self.load_mask_container_1 = roundQGroupBox()
        self.load_mask_container_1.setTitle("Load mask")
        load_mask_container_layout_1 = QGridLayout()
        self.load_mask_container_1.setLayout(load_mask_container_layout_1)
        self.load_mask_from_widget_button = QPushButton("From mask generator")
        self.load_mask_from_file_button = QPushButton("From file")
        self.load_mask_from_widget_button.clicked.connect(self.load_mask_from_widget)
        self.load_mask_from_file_button.clicked.connect(self.load_mask_from_memory)
        load_mask_container_layout_1.addWidget(self.load_mask_from_widget_button, 0, 0)
        load_mask_container_layout_1.addWidget(self.load_mask_from_file_button, 1, 0)

        # Stack page 2
        self.load_mask_container_2 = roundQGroupBox()
        self.load_mask_container_2.setTitle("Load mask")
        load_mask_container_layout_2 = QGridLayout()
        self.load_mask_container_2.setLayout(load_mask_container_layout_2)
        self.load_image = QPushButton("Image")
        self.load_folder = QPushButton("Folder")
        self.load_video = QPushButton("Video")
        self.back_load_mask_container_index0 = QPushButton("Back")

        self.load_image.clicked.connect(self.load_mask_from_file)
        self.load_folder.clicked.connect(self.load_mask_from_folder)
        self.back_load_mask_container_index0.clicked.connect(
            lambda: self.load_mask_container_stack.setCurrentIndex(0)
        )

        load_mask_container_layout_2.addWidget(self.load_image, 0, 0, 1, 2)
        load_mask_container_layout_2.addWidget(self.load_folder, 1, 0, 1, 2)
        load_mask_container_layout_2.addWidget(self.load_video, 2, 0)
        load_mask_container_layout_2.addWidget(
            self.back_load_mask_container_index0, 2, 1
        )

        ## Add layers to stack
        self.load_mask_container_stack.addWidget(self.load_mask_container_1)
        self.load_mask_container_stack.addWidget(self.load_mask_container_2)

        # Detailed settings
        self.settings_container = roundQGroupBox()
        self.settings_container.setTitle("Settings")
        settings_container_layout = QGridLayout()
        self.settings_container.setLayout(settings_container_layout)

        settings_container_layout.addWidget(QLabel("ALP_PROJ_MODE"), 0, 0)
        self.ALP_PROJ_MODE_Combox = QComboBox()
        self.ALP_PROJ_MODE_Combox.addItems(["ALP_MASTER", "ALP_SLAVE"])
        self.ALP_PROJ_MODE_Combox.setToolTip(
            "This ControlType is used to select from an internal or external trigger source."
        )
        settings_container_layout.addWidget(self.ALP_PROJ_MODE_Combox, 0, 1)

        settings_container_layout.addWidget(QLabel("ALP_PROJ_STEP"), 2, 0)
        self.ALP_PROJ_STEP_Combox = QComboBox()
        self.ALP_PROJ_STEP_Combox.addItems(["ALP_DEFAULT", "ALP_EDGE_RISING"])
        self.ALP_PROJ_STEP_Combox.setToolTip(
            "Set frame switching trigger method in the sequence.(Only in ALP_MASTER mode)"
        )
        settings_container_layout.addWidget(self.ALP_PROJ_STEP_Combox, 2, 1)

        settings_container_layout.addWidget(QLabel("ALP_BIN_MODE"), 3, 0)
        self.ALP_ALP_BIN_MODE_Combox = QComboBox()
        self.ALP_ALP_BIN_MODE_Combox.addItems(
            ["ALP_BIN_UNINTERRUPTED", "ALP_BIN_NORMAL"]
        )
        self.ALP_ALP_BIN_MODE_Combox.setToolTip(
            "Binary mode: select from ALP_BIN_NORMAL and ALP_BIN_UNINTERRUPTED (No dark phase between frames)"
        )
        # self.ALP_ALP_BIN_MODE_Combox.currentIndexChanged.connect(self.set_repeat_from_BIN_MODE)
        settings_container_layout.addWidget(self.ALP_ALP_BIN_MODE_Combox, 3, 1)

        self.frame_rate_textbox = QLineEdit()
        self.frame_rate_textbox.setValidator(QtGui.QIntValidator())
        self.frame_rate_textbox.setText("1000000")  # Default 33334

        self.repeat_imgseq_button = QCheckBox()
        self.repeat_imgseq_button.setChecked(True)
        self.repeat_imgseq_button.setToolTip("Repeat the sequence.")

        Illumination_time_label = QLabel("Illumination time(µs):")
        Illumination_time_label.setToolTip(
            "Display time of a single image of the sequence in microseconds. PictureTime is set to minimize the dark time according to illuminationTime, +44 us e.g."
        )

        settings_container_layout.addWidget(Illumination_time_label, 4, 0)
        settings_container_layout.addWidget(self.frame_rate_textbox, 4, 1)
        settings_container_layout.addWidget(QLabel("Repeat sequence:"), 5, 0)
        settings_container_layout.addWidget(self.repeat_imgseq_button, 5, 1)

        box_layout.addWidget(self.connect_button, 0, 0)
        box_layout.addWidget(self.register_button, 0, 1)
        box_layout.addWidget(QLabel("Register with laser:"), 1, 1)
        box_layout.addWidget(self.transform_for_laser_menu, 2, 1, 2, 1)
        box_layout.addWidget(self.project_button, 2, 0)
        box_layout.addWidget(self.clear_button, 3, 0)
        box_layout.addWidget(self.white_project_button, 1, 0)

        box_layout.addWidget(self.load_mask_container_stack, 4, 0, 1, 2)
        box_layout.addWidget(self.settings_container, 5, 0, 1, 2)

        layout.addWidget(self.box)

        self.open_latest_transformation()

    #%%
    def connect(self):
        if self.connect_button.text() == "Connect":
            self.DMD_actuator = DMDActuator.DMDActuator()
            self.connect_button.setText("Disconnect")

        else:
            self.DMD_actuator.disconnect_DMD()
            del self.DMD_actuator
            self.connect_button.setText("Connect")

    def register(self, laser):
        self.sig_start_registration.emit()
        ## Add control for lasers, signal slot should be there in AOTF widget
        registrator = Registrator.DMDRegistator(self.DMD_actuator)
        self.transform[laser] = registrator.registration(registration_pattern="circle")
        self.save_transformation()
        self.sig_finished_registration.emit()

    def check_mask_format_valid(self, mask):
        """
        Check the shape of each frame mask, max project to 2d if it's 3d.
        """
        if len(mask.shape) == 3:
            print("Image is stack; using max projection")
            mask = np.max(mask, axis=2)

        if mask.shape[0] == 1024 and mask.shape[1] == 768:
            mask = mask.transpose()

        elif mask.shape[0] != 768 or mask.shape[1] != 1024:
            print("Image has wrong resolution; should be 1024x768")
            return False, None

        return True, mask

    def load_mask_from_memory(self):
        """
        Open a file manager to browse through files, load image file
        """
        self.load_mask_container_stack.setCurrentIndex(1)

    def load_mask_from_file(self):
        try:
            self.loadFileName, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select file", "./CoordinateManager/Images/", "(*.jpg *.png)"
            )
            image = plt.imread(self.loadFileName)
            # jpg has RGB channels, clean the 3rd channel and make it 2d.
            image_gray = rgb2gray(image)

            check, image = self.check_mask_format_valid(image_gray)

            if check:
                self.DMD_actuator.send_data_to_DMD(image_gray)
                print("Image loaded")
                self.load_mask_container_stack.setCurrentIndex(0)
        except:
            print("Fail to load.")

    def load_mask_from_folder(self):
        """
        Load files from folder using path and save frames in multidimensional array.
        """
        try:
            foldername = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Select folder", "./CoordinateManager/Images/"
            )
            list_dir_raw = sorted(os.listdir(foldername))

            list_dir = [file for file in list_dir_raw if file[-3:] in ["png", "jpg"]]
            list_nr = len(list_dir)
            image_sequence = np.zeros([768, 1024, list_nr])

            for i in range(list_nr):
                single_mask = plt.imread(foldername + "/" + list_dir[i])
                # jpg has RGB channels
                single_mask_gray = rgb2gray(single_mask)
                check, valid_single_mask = self.check_mask_format_valid(
                    single_mask_gray
                )
                if check:
                    image_sequence[:, :, i] = valid_single_mask
                else:
                    return

            self.DMD_actuator.send_data_to_DMD(image_sequence)

            self.load_mask_container_stack.setCurrentIndex(0)
        except:
            print("Fail to load.")

    def load_mask_from_widget(self):
        self.sig_request_mask_coordinates.emit()

    def receive_mask_coordinates(self, sig_from_CoordinateWidget):
        """
        Receive untransformed mask coordinates, transform them, create mask, send mask to DMD.

        PARAMETERS
        ----------
        sig_from_CoordinateWidget : list.  [[signal for first frame], [signal for second frame], ...]
                Signal sent out from CoordinateWidget which contains list of ROIs
                and other parameters for transformation and mask generation.
        """
        for each_mask_key in sig_from_CoordinateWidget:
            print(f"len {len(sig_from_CoordinateWidget)}")
            list_of_rois = sig_from_CoordinateWidget[each_mask_key][0]
            flag_fill_contour = sig_from_CoordinateWidget[each_mask_key][1]
            contour_thickness = sig_from_CoordinateWidget[each_mask_key][2]
            flag_invert_mode = sig_from_CoordinateWidget[each_mask_key][3]
            for_which_laser = sig_from_CoordinateWidget[each_mask_key][4]

            list_of_rois_transformed = self.transform_coordinates(
                list_of_rois, for_which_laser
            )

            mask_single_frame = ProcessImage.CreateBinaryMaskFromRoiCoordinates(
                list_of_rois_transformed,
                fill_contour=flag_fill_contour,
                contour_thickness=contour_thickness,
                invert_mask=flag_invert_mode,
                mask_resolution=(768, 1024),
            )
            fig, axs = plt.subplots(1, 1)
            axs.imshow(mask_single_frame)

            # Here the self.mask is always a 3-dimentional np array with the 3rd axis being number of images.
            if each_mask_key == "mask_1":
                self.mask = mask_single_frame[:, :, np.newaxis]
            else:
                self.mask = np.concatenate(
                    (self.mask, mask_single_frame[:, :, np.newaxis]), axis=2
                )

        self.DMD_actuator.send_data_to_DMD(self.mask)

    def project_full_white(self):
        self.DMD_actuator.send_data_to_DMD(np.ones((1024, 768)))

        repeat = self.repeat_imgseq_button.isChecked()
        frame_time = int(self.frame_rate_textbox.text())
        self.DMD_actuator.set_repeat(repeat)
        self.DMD_actuator.set_timing(frame_time)

        self.DMD_actuator.start_projection()
        self.project_button.setText("Stop projecting")

    def interupt_projection(self):
        if self.project_button.text() == "Stop projecting":
            self.DMD_actuator.stop_projection()
            self.DMD_actuator.free_memory()
            self.project_button.setText("Start projecting")

    def continue_projection(self):
        self.DMD_actuator.stop_projection()
        self.DMD_actuator.free_memory()

        if self.project_button.text() == "Stop projecting":
            self.DMD_actuator.send_data_to_DMD(self.mask)
            self.DMD_actuator.start_projection()

    def transform_coordinates(self, list_of_rois, for_which_laser):
        """
        Receive a list of rois and targeted laser on which the DMD will be shined on, calculate the transformation.
        """
        new_list_of_rois = []
        for roi in list_of_rois:
            new_list_of_rois.append(
                CoordinateTransformations.transform(
                    roi, self.transform[for_which_laser]
                )
            )

        return new_list_of_rois

    def project(self):

        if self.project_button.text() == "Start projecting":
            # Set the settings first.
            self.set_settings()

            print("Projecting")
            self.DMD_actuator.start_projection()
            self.project_button.setText("Stop projecting")
        else:
            self.DMD_actuator.stop_projection()
            self.project_button.setText("Start projecting")

    def set_settings(self):
        """
        If IlluminateTime is also ALP_DEFAULT then
        33334 μs are used according to a frame rate of 30 Hz.
        Otherwise PictureTime is set to minimize the dark
        time according to the specified IlluminateTime.

        The ALP_PROJ_STEP trigger mode is selected using AlpProjControl with ControlType=ALP_PROJ_STEP.
        The table below shows the meaning of different ControlValues.
        ControlValue of ALP_PROJ_STEP Description
        ALP_DEFAULT step forward after each displayed DMD frame. (int = 0)
        ALP_LEVEL_HIGH | LOW step forward if and only if the trigger input is high / low
        ALP_EDGE_RISING | FALLING frame transition depends on a trigger edge. (int = 2009)

        A transition to the next sequence can take place without any gaps, which uses AlpProjStartCont.
        """
        # Set ALP_PROJ_MODE to ALP_MASTER
        ALP_PROJ_MODE = 2300  # 	Select from ALP_MASTER and ALP_SLAVE mode */
        ALP_MASTER = 2301
        ALP_SLAVE = 2302

        if self.ALP_PROJ_MODE_Combox.currentText() == "ALP_MASTER":
            self.DMD_actuator.DMD.ProjControl(
                controlType=ALP_PROJ_MODE, value=ALP_MASTER
            )
        elif self.ALP_PROJ_MODE_Combox.currentText() == "ALP_SLAVE":
            self.DMD_actuator.DMD.ProjControl(
                controlType=ALP_PROJ_MODE, value=ALP_SLAVE
            )

        repeat = self.repeat_imgseq_button.isChecked()
        frame_time = int(self.frame_rate_textbox.text())
        self.DMD_actuator.set_repeat(repeat)
        self.DMD_actuator.set_timing(frame_time)
        print(f"DMD illumination time is set to {frame_time} μs.")

        # Set the clocking of DMD, ALP_DEFAULT = internal clock and ALP_EDGE_RISING = external clock.
        ALP_PROJ_STEP = 2329

        if self.ALP_PROJ_STEP_Combox.currentText() == "ALP_DEFAULT":
            self.DMD_actuator.DMD.ProjControl(controlType=ALP_PROJ_STEP, value=0)
            print("ALP_PROJ_STEP set to ALP_DEFAULT")
        elif self.ALP_PROJ_STEP_Combox.currentText() == "ALP_EDGE_RISING":
            self.DMD_actuator.DMD.ProjControl(controlType=ALP_PROJ_STEP, value=2009)
            print("ALP_PROJ_STEP set to ALP_EDGE_RISING")

        # Set the binary mode of DMD.
        ALP_BIN_MODE = 2104  # 	Binary mode: select from ALP_BIN_NORMAL and ALP_BIN_UNINTERRUPTED (AlpSeqControl)

        ALP_BIN_NORMAL = 2105  # 	Normal operation with progammable dark phase
        ALP_BIN_UNINTERRUPTED = 2106  # 	Operation without dark phase

        if self.ALP_ALP_BIN_MODE_Combox.currentText() == "ALP_BIN_NORMAL":
            self.DMD_actuator.DMD.SeqControl(
                controlType=ALP_BIN_MODE, value=ALP_BIN_NORMAL
            )
            print("set to ALP_BIN_NORMAL")
        elif self.ALP_ALP_BIN_MODE_Combox.currentText() == "ALP_BIN_UNINTERRUPTED":
            self.DMD_actuator.DMD.SeqControl(
                controlType=ALP_BIN_MODE, value=ALP_BIN_UNINTERRUPTED
            )
            print("set to ALP_BIN_UNINTERRUPTED, no frame switching.")

    def clear(self):
        self.DMD_actuator.free_memory()
        self.mask = None

    def set_transformation_saving_location(self, filename):
        self.transformation_file_name = filename

    def save_transformation(self):
        for laser, transform in self.transform.items():
            size = transform.shape[0]
            np.savetxt(
                self.transformation_file_name + laser, np.reshape(transform, (-1, size))
            )

    def open_latest_transformation(self):
        self.transform = {}
        lasers = ["640", "532", "488"]
        for laser in lasers:
            try:
                transform = np.loadtxt(self.transformation_file_name + laser)
            except:
                pass
            else:
                print("Transform for " + laser + " loaded.")
                self.transform[laser] = np.reshape(
                    transform, (transform.shape[1], -1, 2)
                )
                print(self.transform[laser][:, :, 0])
                print(self.transform[laser][:, :, 1])


if __name__ == "__main__":

    def run_app():
        app = QtWidgets.QApplication(sys.argv)
        mainwin = DMDWidget()
        mainwin.show()
        app.exec_()

    run_app()
