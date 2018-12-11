# -*- coding: utf-8 -*-
"""
/***************************************************************************
 AgknowDockWidgetTimeSlider
                                 A QGIS plugin
 Plugin for using the agknow API from geo|cledian
                             -------------------
        begin                : 2018-07-18
        git sha              : $Format:%H$
        copyright            : (C) 2018 by geo|cledian.com
        email                : jsommer@geocledian.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from __future__ import print_function

from builtins import str
import os

from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal, Qt, QBasicTimer
from qgis.PyQt.QtWidgets import QApplication
import qgis.utils

from qgis.core import QgsProject, QgsMessageLog, Qgis

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'agknow_qgis_dockwidget_timeslider.ui'))


class AgknowDockWidgetTimeSlider(QtWidgets.QDockWidget, FORM_CLASS):
    """
     Class for the timeslider dockwidget of the agknow plugin.
    """
    closingPlugin = pyqtSignal()
    productChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        """Constructor."""
        super(AgknowDockWidgetTimeSlider, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        # GUI Events
        # lambda keyword allows the button itself to be passed
        #https://www.tutorialspoint.com/pyqt/pyqt_qradiobutton_widget.htm
        self.rdBtnVisible.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnVisible))
        self.rdBtnVitality.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnVitality))
        self.rdBtnVariations.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnVariations))
        self.rdBtnNDRE1.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnNDRE1))
        self.rdBtnNDRE2.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnNDRE2))
        self.rdBtnNDWI.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnNDWI))
        self.rdBtnSAVI.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnSAVI))
        self.rdBtnEVI2.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnEVI2))
        self.rdBtnCIRE.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnCIRE))
        self.rdBtnNDVI.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnNDVI))
        self.rdBtnRefl.toggled.connect(lambda: self.rdBtnProductState_toggled(self.rdBtnRefl))

        self.sliderTime.valueChanged.connect(self.sliderValue_changed)
        self.btnTimePlay.clicked.connect(self.btnTimePlay_clicked)
        self.btnTimeBackward.clicked.connect(self.btnTimeBackward_clicked)
        self.btnTimeForward.clicked.connect(self.btnTimeForward_clicked)

        self.product = "vitality"
        self.rasters = [] # it's a list here - a dict in agknow_qgis_dockwidget.py
        self.data_source = "sentinel2"
        self.current_parcel_id = None

        # timeslider
        self.timer = QBasicTimer()
        self.step = 0

        self.iface = qgis.utils.iface

    def set_data_source(self, data_source):
        """
         Setter for the data_source (landsat-8 or sentinel-2).
        """
        self.data_source = data_source

        self.toggle_products_data_source_compatibility()

    def set_product(self, product):
        """
         Setter for the product (vitality, variations, visible, etc).
        """
        self.product = product

        # notify slots of change
        self.productChanged.emit(product)

    def set_current_parcel_id(self, parcel_id):
        """
         Setter for the current parcel_id.
        """
        self.current_parcel_id = parcel_id

    def timerEvent(self, e):
        """
         Event handler for the timer.
        :param e:
        """
        print("timerEvent()")

        if self.step == self.sliderTime.maximum():
            self.timer.stop()
            self.step = 0  #reset step
            return
        else:
            self.step = self.step + 1

            self.sliderTime.setValue(self.sliderTime.value()+1)


    def rdBtnProductState_toggled(self, btn):
        """
         Handles the toggled event of the given radio button.

        :param btn: radio button (QRadioButton)
        """
        # trigger update
        # if radio button is checked at the end
        if btn.isChecked():

            if btn.text().lower() == "refl.":
                self.set_product("reflectances")
            else:
                self.set_product(btn.text().lower())

            parcel_id = self.current_parcel_id

            if len(self.rasters) > 0:

                # find subgroup
                root = QgsProject.instance().layerTreeRoot()
                parcel_group = root.findGroup("parcel id: {0}".format(parcel_id))

                # select active layer for identity e.g.
                self.set_layer_active_toc(parcel_id)

                if parcel_group is not None:
                    self.toggle_products(parcel_group)


    def set_layer_active_toc(self, parcel_id):
        """
         Sets the group layer of the given parcel ID in the TOC to active.

        :param parcel_id: parcel's ID (integer)
        """
        # take the first layer of the group "parcel id: - source - product"
        data_source_group = self.find_data_source_group(parcel_id, self.product, self.data_source)

        # layer name
        date = self.rasters[0]["date"]
        raster_id = self.rasters[0]["raster_id"]
        activeLyrName = date + " - " + str(raster_id)

        if data_source_group is not None:

            for lyr in data_source_group.findLayers():

                #print("searching for {0}..".format(activeLyrName))

                # QGIS >= 2.18.1 : name(), QGIS 2.18.0 : layerName()
                if lyr.name() == activeLyrName:

                    # QgsLayerTreeLayer to QgsMapLayer per .layer()
                    #print("setting lyr {0} active".format(lyr.layerName()))
                    self.iface.setActiveLayer(lyr.layer())

        else:
            pass
            #print("data_source_group not found: {0} - {1} - {2}".format(parcel_id, self.product, self.data_source))

    def sliderValue_changed(self):
        """
         Handles the value changed event of the timeslider.
        """

        if len(self.rasters) > 0:
            #print(self.sliderTime.value())

            idx = self.sliderTime.value()

            #set current raster to visible - the rest invisible

            # get data from position in self.rasters
            product_id = self.product + " " #whitespace!
            data_source = self.rasters[idx]["source"]
            parcel_id = self.rasters[idx]["parcel_id"]
            raster_id = self.rasters[idx]["raster_id"]
            date = self.rasters[idx]["date"]

            #print(product_id, data_source, parcel_id, raster_id, date)

            activeLyrName = "{0}|{1}|{2}|{3}".format(product_id.strip(), date, raster_id, data_source) #date + " - " + str(raster_id)

            #print(activeLyrName)

            self.toggle_image_layer(activeLyrName, data_source, parcel_id, product_id)

        else:
            QgsMessageLog.logMessage("AgknowDockWidgetTimeSlider - sliderValue_changed() - rasters are not set!",
                                     "agknow",
                                     Qgis.Critical)


    def toggle_image_layer(self, activeLyrName, data_source, parcel_id, product_id):
        """
         Toggles all other image layers off except the given activeLayer.

        :param activeLyrName: active layer group (string)
        :param data_source: landsat-8 or sentinel-2 (string)
        :param parcel_id: parcel's ID (integer)
        :param product_id: product id: visible, vitality, variations, etc. (string)
        """
        # find subgroup
        data_source_group = self.find_data_source_group(parcel_id, product_id, data_source)

        if data_source_group is not None:

            for lyr in data_source_group.findLayers():
                # QGIS 2.18.1 : name(), QGIS 2.18.0 : layerName()
                if lyr.name() == activeLyrName:
                    # set active layer visible
                    lyr.setItemVisibilityChecked(Qt.Checked)
                    # select active layer for identity e.g.
                    # QgsLayerTreeLayer to QgsMapLayer per .layer()
                    self.iface.setActiveLayer(lyr.layer())
                else:
                    lyr.setItemVisibilityChecked(Qt.Unchecked)


    def find_data_source_group(self, parcel_id, product_id, data_source):
        """
         Returns the data source group layer of the TOC for the given parcel id, product and data source.

        :param parcel_id: parcel's ID (integer)
        :param product_id: product id: visible, vitality, variations, etc. (string)
        :param data_source: landsat-8 or sentinel-2 (string)

        :return: data_source_group (QgsLayerTreeGroup)
        """
        root = QgsProject.instance().layerTreeRoot()
        parcel_group = root.findGroup("parcel id: {0}".format(parcel_id))

        if parcel_group is not None:
            #print("parcel group found")
            product_group = parcel_group.findGroup(product_id)
            #print(product_group)

            if product_group is not None:
                #print("product group found")
                data_source_group = product_group.findGroup(data_source)

                return data_source_group


    def toggle_products(self, parcel_group):
        """
         Toggle all other product groups off except the given parcel_group.

        :param parcel_group: (QgsLayerTreeGroup)
        """
        data_source_list = ["landsat8", "sentinel2"]
        matrix = {"landsat8": ["visible", "vitality", "variations"],
                  "sentinel2": ["visible", "vitality", "variations", "reflectances", "ndvi", "ndre1", "ndre2", "ndre3",
                                "ndwi", "savi", "evi2", "cire"]
                  }

        # turn off other data_source groups
        for ds in data_source_list:
            #print("checking {0}..".format(ds))
            for p in matrix[ds]:
                #print("checking product {0}..".format(p))
                pg = parcel_group.findGroup(p + " ")

                if pg is not None:
                    #print("group {0} found!".format(p))
                    g = pg.findGroup(ds)

                    if g is not None:
                        if p == self.product and ds == self.data_source:
                            #print("group {0} visible".format(ds))
                            g.setItemVisibilityChecked(Qt.Checked)
                        else:
                            #print("group {0} invisible!".format(ds))
                            g.setItemVisibilityChecked(Qt.Unchecked)

    def toggle_products_data_source_compatibility(self):
        """
         Handles radio buttons for compatibility of products & data_source
        """
        print("toggle_products_data_source_compatibility()")
        matrix = {"landsat8": ["Visible", "Vitality", "Variations"],
                  "sentinel2": ["Visible", "Vitality", "Variations", "Refl.", "NDVI", "NDRE1", "NDRE2", "NDRE3",
                                    "NDWI", "SAVI", "EVI2", "CIRE"]
                   }
        radioBtns = [self.rdBtnVisible, self.rdBtnVitality, self.rdBtnVariations,
                        self.rdBtnNDRE1, self.rdBtnNDRE2, self.rdBtnNDWI, self.rdBtnSAVI, self.rdBtnEVI2,
                        self.rdBtnCIRE, self.rdBtnNDVI, self.rdBtnRefl]

        for rdBtn in radioBtns:
            # disable all other radio buttons
            if rdBtn.text() in matrix[self.data_source]:
                rdBtn.setEnabled(True)
            else:
                rdBtn.setEnabled(False)

        #TODO: if data source disables product - select another product
        # leads to segmentation faults at the moment because several threads are started then
        #for rdBtn in radioBtns:
        #    # check if selected radio button is disabled
        #    if rdBtn.isChecked() and not rdBtn.isEnabled():
        #        # if so take the first of possible radio buttons
        #        rdBtnToCheckName = matrix[self.data_source][0]
        #        print(rdBtnToCheckName)
        #        for r in radioBtns:
        #            if r.text() == rdBtnToCheckName:
        #                r.setChecked(Qt.Checked)

    def btnTimePlay_clicked(self):
        """
         Handles the click event of the Button btnTimePlay.
        """
        self.btnTimePlay.setText(" || ")
        interval = 1000 #ms

        # stop timer if it is already active
        if self.timer.isActive():
            self.btnTimePlay.setText(" > ")
            self.timer.stop()
            # reset timer
            self.step = 0
            self.sliderTime.setValue(0)

        # start timer
        else:
            self.timer.start(interval, self)


    def btnTimeForward_clicked(self):
        """
         Handles the click event of the Button btnTimeForward.
        """
        self.sliderTime.setValue(self.sliderTime.value()+1)


    def btnTimeBackward_clicked(self):
        """
         Handles the click event of the Button btnTimeBackward.
        """
        self.sliderTime.setValue(self.sliderTime.value()-1)


    def reload_images(self, rasters):
        """
         Reloads images for the given rasters.
         :param rasters: ()
        """
        #print("reload_images({0})".format(rasters))

        if rasters is not None:
            self.sliderTime.setRange(0, len(rasters)-1)
            self.sliderTime.setTickInterval = 1
            self.rasters = rasters

            if len(self.rasters) > 0:
                #print(self.rasters)
                parcel_id = self.rasters[0]["parcel_id"]

                QgsMessageLog.logMessage("AgknowDockWidgetTimeSlider - activating parcel {0}..".format(parcel_id),
                                         "agknow",
                                         Qgis.Info)
                # select first image layer active in toc for identity e.g.
                self.set_layer_active_toc(parcel_id)

        else:
            QgsMessageLog.logMessage("AgknowDockWidgetTimeSlider - rasters is None!", "agknow",
                                     Qgis.Warning)


    def closeEvent(self, event):
        """
         Handles the close event of the class.
        :param event:
        """
        self.closingPlugin.emit()
        event.accept()

