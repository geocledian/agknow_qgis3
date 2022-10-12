# -*- coding: utf-8 -*-
"""
/***************************************************************************
 AgknowDockWidget
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
from __future__ import absolute_import

from builtins import next
from builtins import str
from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal, pyqtSlot, QVariant, Qt, QThread, QDate
from qgis.PyQt.QtWidgets import QApplication,QFileDialog
import qgis.utils
from qgis._core import QgsDataProvider

from qgis.core import QgsRasterLayer, QgsPoint, QgsVectorLayer, QgsGeometry,  \
    QgsFields, QgsField, QgsFeatureRequest, QgsExpression, QgsProject, Qgis, QgsMessageLog, QgsLayerTreeLayer, \
     QgsMapLayerProxyModel

from .agknow_worker import *

from . import agknow_utils

import json
import os
import datetime
from osgeo import gdal

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'agknow_qgis_dockwidget_base.ui'))


class AgknowDockWidget(QtWidgets.QDockWidget, FORM_CLASS):
    """
     Class for main dockwidget of the agknow plugin with all relevant controls.
    """
    closingPlugin = pyqtSignal()
    imagesReloaded = pyqtSignal(list)
    dataSourceChanged = pyqtSignal(str)
    parcelIdChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        """Constructor."""
        super(AgknowDockWidget, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)


        # lambda keyword allows the button itself to be passed
        #https://www.tutorialspoint.com/pyqt/pyqt_qradiobutton_widget.htm
        self.rdBtnDataSourceLandsat.toggled.connect(lambda: self.rdBtnDataSourceState_toggled(self.rdBtnDataSourceLandsat))
        self.rdBtnDataSourceSentinel.toggled.connect(lambda: self.rdBtnDataSourceState_toggled(self.rdBtnDataSourceSentinel))
        self.rdBtnDataSourceAll.toggled.connect(lambda: self.rdBtnDataSourceState_toggled(self.rdBtnDataSourceAll))

        self.cbPolygonLayer.setFilters(QgsMapLayerProxyModel.PolygonLayer)

        # Hide "Please select a feature from the chosen polygon layer!" text
        self.lblRegister.setVisible(False)

        self.iface = qgis.utils.iface
        self.canvas = self.iface.mapCanvas()

        self.plugin_path = os.path.dirname(__file__)
        self.style_path = self.plugin_path + os.sep + "parcels-style-yellow.qml"

        self.current_project_epsg = self.get_current_project_epsg()

        QgsMessageLog.logMessage("Current EPSG: {0}".format(self.current_project_epsg), 'agknow', Qgis.Info)

        # Defaults to EPSG 4326 if SRS not set
        if self.current_project_epsg is None:
            self.current_project_epsg = 4326

        # just to be sure
        try:
            self.remove_parcel_lyr()
        except:
            pass

        self.parcelLyr = self.init_parcel_lyr()
        self.registerLyr = None

        self.parcel_ids = []

        self.init_image_lyr()

        self.settings = {"parcel_download_mode": "one-by-one",
                         "image_format": "tif",
                         "connected": False}

        self.api_version = "/agknow/api/v" + str(self.cbAPIVersion.currentText())
        self.utils = agknow_utils.AgknowUtils(self.api_version)

        self.product = "vitality"
        self.data_source = "sentinel2"

        self.register_data = { u"crop": "",
                               u"name": "",
                               u"planting": "",
                               u"harvest": "",
                               u"entity": "",
                               u"geometry": ""
                            }

        self.parcel_id_to_set = None

        # {raster_group_id: [raster data in json format]}
        # raster_group_id = "{0}_{1}_{2}_{3}".format(parcel_id, self.product_id, self.data_source, self.img_format)
        self.rasters = {}

        # GUI Events
        self.btnConnect.clicked.connect(self.btnConnect_clicked)
        self.cbResultsIDName.currentIndexChanged.connect(self.cbResultsIDName_currentIndexChanged)
        self.btnRefresh.clicked.connect(self.btnRefresh_clicked)
        self.btnRegister.clicked.connect(self.btnRegister_clicked)
        self.cbPolygonLayer.currentIndexChanged.connect(self.cbPolygonLayer_currentIndexChanged)
        self.btnSaveImgs.clicked.connect(self.btnSaveImgs_clicked)
        self.cbAPIVersion.currentIndexChanged.connect(self.cbAPIVersion_currentIndexChanged)

        # reset register data
        self.clear_register_data()

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)


    def get_current_project_epsg(self):
        """
         Gets the current EPSG Code of the QGIS project.

        :return: EPSG Code (integer)
        """
        # authid() returns EPSG:99999
        return int(self.iface.mapCanvas().mapSettings().destinationCrs().authid().split(":")[1])

    def get_layer_epsg(self, layer):
        """
         Gets the EPSG Code of the given layer.

        :param layer: QgsMapLayer
        :return: EPSG Code (integer)
        """

        return int(layer.crs().authid().split(":")[1])

    def set_data_source(self, data_source):
        """
         Setter for the data_source (landsat-8 or sentinel-2).
        """
        QgsMessageLog.logMessage("Selected Data source: {0}".format(data_source), 'agknow', Qgis.Info)
        self.data_source = data_source

        # notify slots on change of data_source
        self.dataSourceChanged.emit(self.data_source)

    def set_product(self, product):
        """
         Setter for the product (vitality, variations, visible, etc).
        """
        QgsMessageLog.logMessage("Selected Product: {0}".format(product), 'agknow', Qgis.Info)
        self.product = product

        self.handle_product_change(product)


    def map_known_data_model(self, feature):
        """
         Maps the feature's data to the agknowledge REST data model
        :param feature: QgsFeature
        """

        # try to map values from known fields to the internal data model
        try:
            self.tbRegisterCrop.setText(feature["crop"])
        except KeyError:
            self.tbRegisterCrop.setText("")
        except:
            QgsMessageLog.logMessage("Error mapping data from register to internal layer!", 'agknow',
                                     Qgis.Warning)

        try:
            self.tbRegisterName.setText(feature["name"])
        except KeyError:
            self.tbRegisterName.setText("")
        except:
            QgsMessageLog.logMessage("Error mapping data from register to internal layer!", 'agknow',
                                     Qgis.Warning)

        # test the more unlikely first - may be overriden by the following field
        try:
            if feature["seeding"] is not None:
                # for text field with date in it
                if type(feature["seeding"]) is type("test"):
                    # for text field (QString) in ISO Format (YYYY-MM-DD)
                    d = QDate.fromString(feature["seeding"], Qt.ISODate)
                elif type(feature["seeding"]) is type(QDate):
                    # for date field (QDate)
                    d = feature["seeding"]

                self.tbRegisterSeeding.setDate(d)

        except KeyError:
            self.tbRegisterSeeding.setDate(QDate.fromString("{0}-01-01".format(datetime.datetime.now().year), Qt.ISODate))
        except:
            QgsMessageLog.logMessage("Error mapping data from register to internal layer!", 'agknow',
					Qgis.Warning)
        try:
            if feature["planting"] is not None:
                # for text field with date in it
                if type(feature["planting"]) is type("test"):
                    # for text field (QString) in ISO Format (YYYY-MM-DD)
                    d = QDate.fromString(feature["planting"], Qt.ISODate)
                elif type(feature["planting"]) is type(QDate):
                    # for date field (QDate)
                    d = feature["planting"]

                self.tbRegisterSeeding.setDate(d)

        except KeyError:
            self.tbRegisterSeeding.setDate(QDate.fromString("{0}-01-01".format(datetime.datetime.now().year), Qt.ISODate))
        except:
            QgsMessageLog.logMessage("Error mapping data from register to internal layer!", 'agknow',
                                     Qgis.Warning)

        # test the more unlikely first - may be overriden by the following field
        try:
            if feature["cutting"] is not None:
                # for text field with date in it
                if type(feature["cutting"]) is type("test"):
                    # for text field (QString) in ISO Format (YYYY-MM-DD)
                    d = QDate.fromString(feature["cutting"], Qt.ISODate)
                elif type(feature["cutting"]) is type(QDate):
                    # for date field (QDate)
                    d = feature["cutting"]

                self.tbRegisterHarvest.setDate(d)

        except KeyError:
            self.tbRegisterHarvest.setDate(QDate.fromString("{0}-12-31".format(datetime.datetime.now().year), Qt.ISODate))
        except:
            QgsMessageLog.logMessage("Error mapping data from register to internal layer!", 'agknow',
                                     Qgis.Warning)

        try:
            if feature["harvest"] is not None:
                # for text field with date in it
                if type(feature["harvest"]) is type("test"):
                    # for text field (QString) in ISO Format (YYYY-MM-DD)
                    d = QDate.fromString(feature["harvest"], Qt.ISODate)
                elif type(feature["harvest"]) is type(QDate):
                    # for date field (QDate)
                    d = feature["harvest"]

                self.tbRegisterHarvest.setDate(d)

        except KeyError:
            self.tbRegisterHarvest.setDate(QDate.fromString("{0}-12-31".format(datetime.datetime.now().year), Qt.ISODate))
        except:
            QgsMessageLog.logMessage("Error mapping data from register to internal layer!", 'agknow',
                                     Qgis.Warning)
        try:
            self.tbRegisterEntity.setText(feature["entity"])
        except KeyError:
            self.tbRegisterEntity.setText("")
        except:
            QgsMessageLog.logMessage("Error mapping data from register to internal layer!", 'agknow',
                                     Qgis.Warning)

    def handle_product_change(self, product):
        """
         Handles the change of the product.
        :param product: vitality, variations, visible, etc  (string)
        """
        if product == "reflectances":
            self.freeze_image_format_to_tiff()
        elif product == "visible":
            self.freeze_image_format_to_png()
        else:
            self.enable_image_format()

        parcel_id = self.get_current_parcel_id()

        # notify slots on change
        self.parcelIdChanged.emit(parcel_id)

        self.init_group_layers(parcel_id, self.product)

        self.update_parcel_data_and_images()


    def get_parcelLyr(self):
        """
         Getter for the parcel layer.
        :return: parcel layer of agknow.
        """
        return self.parcelLyr

    def init_progressBar(self, min_value=0, max_value=100):
        """
         Initializes the progress bar within with the given min and max value.

        :param min_value: (integer)
        :param max_value: (integer)
        """

        # clear the message bar
        self.iface.messageBar().clearWidgets()
        # set a new message bar
        self.progressMessageBar = self.iface.messageBar()
        self.progress = QtWidgets.QProgressBar()

        # Maximum is set to 100, making it easy to work with percentage of completion
        # If minimum and maximum both are set to 0, the bar shows a busy indicator instead of a percentage of steps.
        # http://pyqt.sourceforge.net/Docs/PyQt4/qprogressbar.html
        self.progress.setMinimum(min_value)
        self.progress.setMaximum(max_value)

        # pass the progress bar to the message Bar
        self.progressMessageBar.pushWidget(self.progress)

    def init_parcel_lyr(self):
        """
         Initializes the parcel layer (QgsVectorLayer).

         :return parcelLyr (QgsVectorLayer)
        """
        print("init_parcel_lyr()")
        parcelLyr = QgsVectorLayer("Polygon?crs=epsg:{0}".format(self.get_current_project_epsg()), "parcels", "memory")

        root = self.iface.layerTreeCanvasBridge().rootGroup()

        # False indicates, that the layer is not shown yet
        QgsProject.instance().addMapLayer(parcelLyr, False)
        self.set_layer_style(parcelLyr, self.style_path)

        # ensure that parcel layer is always on top
        node_layer = QgsLayerTreeLayer(parcelLyr)
        root.insertChildNode(0, node_layer)

        fields = QgsFields()
        fields.append(QgsField("parcel_id", QVariant.Int))
        fields.append(QgsField("name", QVariant.String))
        fields.append(QgsField("entity", QVariant.String))
        fields.append(QgsField("crop", QVariant.String))
        fields.append(QgsField("startdate", QVariant.String))
        fields.append(QgsField("enddate", QVariant.String))
        fields.append(QgsField("planting", QVariant.String))
        fields.append(QgsField("harvest", QVariant.String))
        fields.append(QgsField("area", QVariant.Double))
        fields.append(QgsField("apikey", QVariant.String))
        fields.append(QgsField("host", QVariant.String))

        pr = parcelLyr.dataProvider()
        pr.addAttributes(fields)
        parcelLyr.updateFields()  # tell the vector layer to fetch changes from the provider

        self.iface.setActiveLayer(parcelLyr)

        return parcelLyr

    def remove_parcel_lyr(self):
        """
         Removes the agknow parcel layer from the TOC.
        """
        QgsProject.instance().removeMapLayer(self.parcelLyr)

    def init_image_lyr(self):
        """
         Initialzes the image group layer.
        """
        # root node
        root = QgsProject.instance().layerTreeRoot()

        # add new images group
        images_group = root.addGroup("images")

    def closeEvent(self, event):
        """
          Handles the close event of the class.
         :param event:
         """
        self.closingPlugin.emit()
        event.accept()

    # GUI Event Handlers
    def btnConnect_clicked(self):
        """
         Handles the click event on btnConnect.
        """
        print("btnConnect_clicked()")

        # Reset connection
        if self.settings["connected"]:
            self.disconnect()
        else:
            self.connect()

    def btnSaveImgs_clicked(self):
        """
         Handles the click event on btnSaveImgs
        """
        self.exportImages()


    def exportImages(self):
        """
         Exports all images in the TOC of the agknow plugin to the selected directory on disk
         and changes datasource from memory map to disk files.
        """
        directory = str(QFileDialog.getExistingDirectory(self, "Select Directory"))

        print("Selected directory: {0}".format(directory))

        for key in self.rasters.keys():
            rasterList = self.rasters[key]
            #print(rasterList)

            '''[{'product': 'vitality', 'statistics': {}, 'raster_id': 4604179, 'parcel_id': 132060,
             'bounds': [[50.8391215495772, 7.77318200000001], [50.844141, 7.78393796519178]], 'source': 'sentinel2',
             'date': '2019-01-20', 'png': '/parcels/132060/vitality/sentinel2/4604179.png',
             'mmap_name': '/vsimem/213570cbc57a4204a9ea809210324c02'}, ...]'''

            new_rasters = []
            for raster in rasterList:
                # mmap_name may also be a persistent path on disk!
                mmap_name = raster["mmap_name"]
                print(mmap_name)

                raster_id = raster["raster_id"]
                date = raster["date"]
                img_url = raster["png"]
                parcel_id = raster["parcel_id"]
                product_id = raster["product"]
                data_source = raster["source"]

                out_path = os.path.join(directory, f"agknow-{datetime.date.today()}", os.sep.join(img_url.lstrip('/').split('/')))

                out_path = "{0}_{1}.{2}".format(out_path.strip(".png"), date, self.settings["image_format"])
                out_path_subdir = os.path.dirname(out_path)

                if not os.path.exists(out_path_subdir):
                    os.makedirs(out_path_subdir, exist_ok=True)

                print("Exporting to {0}..".format(out_path))
                self.utils.exportGDALraster(mmap_name, out_path)

                # change mmap_name in layers datasource

                if mmap_name.startswith("/vsimem"):
                    # memory clean up
                    gdal.Unlink(mmap_name)

                # find in TOC
                root = QgsProject.instance().layerTreeRoot()

                product_group = root.findGroup("parcel id: {0}".format(parcel_id)).findGroup(
                    product_id + " ").findGroup(
                    data_source)

                # get layer of this group
                for child in product_group.children():
                    # layername: vitality|2021-09-25|8315|sentinel2
                    if child.name() == f"{product_id}|{date}|{raster_id}|{data_source}":
                        rLry = child.layer()
                        rLry.setDataSource(out_path, child.name(), "gdal", QgsDataProvider.ProviderOptions())

                # update mmap_name with new path
                raster["mmap_name"] = out_path
                new_rasters.append(raster)

            # change mmap_name in self.rasters dictionary
            self.rasters[key] = new_rasters


    def disconnect(self):
        """
         Disconnects from agknowledge REST API.
        """

        # clear combobox, lyr, parcel_ids
        self.cbResultsIDName.clear()
        self.settings["connected"] = False
        self.deactivate_connecting_state()
        self.show_disconnected_state()

    def connect(self):
        """
         Connect to the agknowledge REST API.
        """

        # clear combobox, lyr, parcel_ids
        self.cbResultsIDName.clear()
        try:
            self.remove_parcel_lyr()

        except Exception as e:
            QgsMessageLog.logMessage("Error removing parcel layer!", 'agknow',
                                     Qgis.Warning)

        self.activate_connecting_state()
        # wait cursor
        QApplication.setOverrideCursor(Qt.WaitCursor)

        self.parcelLyr = self.init_parcel_lyr()
        self.parcel_ids = []
        self.reset_toc()
        self.rasters = {}
        self.read_agknow_settings()

        api_key = self.tbAPIKey.text()
        host_url = self.tbHostURL.text()
        
        base_url = host_url + self.api_version

        # limited to 1000 at the moment
        # TODO: paging
        limit = 2500
        offset = 0 #6000
        params = "/parcels/?key={0}&limit={1}&offset={2}".format(api_key, limit, offset)
        # async with worker
        # set up progress bar
        self.init_progressBar(min_value=0, max_value=0)
        kwargs = {"base_url": base_url, "params": params, "ssl_verify": True, "api_version": self.api_version}
        print(kwargs)
        self.startWorker(_runMethod="http_get",
                         _finishedEvtMethod="get_parcel_base_data_finished",
                         _errorEvtMethod="get_parcel_base_data_error",
                         **kwargs)

    def cbResultsIDName_currentIndexChanged(self):
        """
         Handles the currentIndexChanged event on cbResultsIDName (i.e. when the user chooses another parcel from
         the combobox.
        """
        print("cbResultsIDName_currentIndexChanged()")

        self.activate_connecting_state()

        # notify slot on change
        self.parcelIdChanged.emit(self.get_current_parcel_id())

        self.update_parcel_data_and_images()

        # find subgroup
        root = QgsProject.instance().layerTreeRoot()
        parcel_group = root.findGroup("parcel id: {0}".format(self.get_current_parcel_id()))

        if parcel_group is not None:
            self.toggle_data_sources(parcel_group)


    def cbPolygonLayer_currentIndexChanged(self):
        """
         Handles the currentIndexChanged event on cbPolygonLayer (i.e. when the user chooses another layer from
         the combobox.
        """
        print("cbPolygonLayer_currentIndexChanged()")

        lyr = self.get_current_register_layer()

        if lyr is not None:

            self.iface.mainWindow().statusBar().showMessage(self.lblRegister.text())
            self.lblRegister.setVisible(True)

            #print(lyr.name())
            self.registerLyr = lyr

            # also activate layer in TOC on changed section
            self.iface.setActiveLayer(lyr)

            #connect to selectedFeatures event
            self.registerLyr.selectionChanged.connect(self.registerLyr_selectionChanged)

    def registerLyr_selectionChanged(self):
        """
         Handles the selectionChanged event of the registerLayer.
        """

        # only if user wants to register
        if self.chxBoxRegister.isChecked():
            if len(self.registerLyr.selectedFeatures()) > 0:
                if len(self.registerLyr.selectedFeatures()) == 1:
                    self.iface.mainWindow().statusBar().clearMessage()
                    self.lblRegister.setVisible(False)
                    self.btnRegister.setEnabled(True)
                    self.map_known_data_model(self.registerLyr.selectedFeatures()[0])
                else:
                    self.lblRegister.setVisible(True)
                    self.btnRegister.setEnabled(False)
            else:
                self.iface.mainWindow().statusBar().showMessage(self.lblRegister.text())
                # clear attribute data
                self.clear_register_data()
                self.lblRegister.setVisible(True)
                self.btnRegister.setEnabled(False)

    def cbAPIVersion_currentIndexChanged(self):
        """
         Handles the currentIndexChanged event of the cbAPIVersion combobox.
        """
        self.api_version = "/agknow/api/v" + str(self.cbAPIVersion.currentText())
        self.utils = agknow_utils.AgknowUtils(self.api_version)


    def clear_register_data(self):
        """
         Clears all data from the GUI elements and internal storage of register_data.
        """
        self.register_data.clear()
        self.tbRegisterName.setText("")
        self.tbRegisterCrop.setText("")
        self.tbRegisterEntity.setText("")
        # Set default values for the current year as dates
        current_year = datetime.datetime.now().year
        self.tbRegisterSeeding.setDate(QDate.fromString("{0}-01-01".format(current_year), Qt.ISODate))
        self.tbRegisterHarvest.setDate(QDate.fromString("{0}-12-31".format(current_year), Qt.ISODate))

    def register_feature(self, register_data):
        """
         Register the given QgsFeature in the agknow API.
         :param register_data: feature with geometry and attributes to register (QgsFeature)
        """
        print("register_feature()")

        # async registering
        api_key = self.tbAPIKey.text()
        host_url = self.tbHostURL.text()
        
        base_url = host_url + self.api_version
        params = "/parcels/?key=" + api_key

        kwargs = {"base_url": base_url, "params": params, "feature_to_register": register_data,
                  "ssl_verify": True, "api_key": api_key, "geometry_epsg": self.get_layer_epsg(self.get_current_register_layer()),
                  "api_version": self.api_version}

        self.startWorker(_runMethod="register_feature",
                         _finishedEvtMethod="register_feature_finished",
                         _errorEvtMethod="register_feature_error",
                         **kwargs)

    def btnRefresh_clicked(self):
        """
         Handles the click event on btnRefresh.
        """

        self.activate_connecting_state()

        self.refresh_data()

    def btnRegister_clicked(self):
        """
         Handles the click event on btnRegister.
        """
        self.activate_connecting_state()

        features = []
        # get the selected features
        if self.registerLyr is not None:
            if len(self.registerLyr.selectedFeatures()) > 0:
                if len(self.registerLyr.selectedFeatures()) == 1:

                    # set attribute data again if changed through user
                    self.register_data[u"crop"] = self.tbRegisterCrop.text()
                    self.register_data[u"name"] = self.tbRegisterName.text()

                    # QDate to string conversion Qt.ISODate -> YYYY-MM-DD
                    self.register_data[u"planting"] = self.tbRegisterSeeding.date().toString(Qt.ISODate)
                    self.register_data[u"harvest"] = self.tbRegisterHarvest.date().toString(Qt.ISODate)

                    self.register_data[u"entity"] = self.tbRegisterEntity.text()
                    # but take the geometry from the selected feature
                    # DON't: self.registerLyr.selectedFeatures()[0].geometry().asWkt() --> segmentation fault!
                    # Do it this way
                    feat = self.registerLyr.selectedFeatures()[0]
                    self.register_data[u"geometry"] = feat.geometry().asWkt()

                    self.register_feature(self.register_data)

                elif len(self.registerLyr.selectedFeatures()) > 1:
                    QgsMessageLog.logMessage("More than one feature selected - cannot proceed!", "agknow", Qgis.Critical)

        self.deactivate_connecting_state()

    def get_current_register_layer(self):
        """
         Returns the current selected layer (QgsMapLayer) from which feature may be registered in the API.
        """
        return self.cbPolygonLayer.currentLayer()

    def refresh_data(self):
        """
         Refresh data for current parcel.
        """
        parcel_id = self.get_current_parcel_id()

        self.clear_images_toc(parcel_id, self.product, self.data_source)
        self.rasters = {}
        self.read_agknow_settings()

        api_key = self.tbAPIKey.text()
        host_url = self.tbHostURL.text()
        
        base_url = host_url + self.api_version

        self.update_parcel_images(api_key, base_url, [parcel_id])

    def rdBtnDataSourceState_toggled(self, btn):
        """
         Handles the toggled event of the given radio button.

        :param btn: radio button (QRadioButton)
        """
        # wait cursor
        QApplication.setOverrideCursor(Qt.WaitCursor)

        if btn.isChecked():

            if btn.text() == "Landsat-8":
                data_source = "landsat8"

            if btn.text() == "Sentinel-2":
                data_source = "sentinel2"

            # this may lead to an image refresh
            # if we set another product in in toggle_products_data_source_compatibility()!
            # So this should not be done!
            self.set_data_source(data_source)

            # update images in toc
            self.update_parcel_data_and_images()

            # find subgroup
            root = QgsProject.instance().layerTreeRoot()
            parcel_group = root.findGroup("parcel id: {0}".format(self.get_current_parcel_id()))

            if parcel_group is not None:
                self.toggle_data_sources(parcel_group)

        # restore cursor
        QApplication.restoreOverrideCursor()

    def toggle_data_sources(self, parcel_group):
        """
         Toggle all other data_source groups off except the given data_source and parcel group.

        :param data_source: "landsat8" or "sentinel2" (string)
        :param parcel_group: (QgsLayerTreeGroup)
        """
        print("toggle_data_sources()")

        data_source_list = ["landsat8", "sentinel2"]
        matrix = {"landsat8": ["visible", "vitality", "variations"],
                  "sentinel2": ["visible", "vitality", "variations", "reflectances", "ndvi", "ndre1", "ndre2", "ndre3",
                                    "ndwi", "savi", "evi2", "cire"]}

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


    def read_agknow_settings(self):
        """
         Reads the settings from the GUI.
        """
        if self.rdBtnParcelDownloadOne.isChecked():
            self.settings["parcel_download_mode"] = "one-by-one"
        if self.rdBtnParcelDownloadAll.isChecked():
            self.settings["parcel_download_mode"] = "all-at-once"
        if self.rdBtnImgOptPNG.isChecked():
            self.settings["image_format"] = "png"
        if self.rdBtnImgOptTiff.isChecked():
            self.settings["image_format"] = "tif"

    def get_current_parcel_id(self):
        """
         Returns the current parcel id.
        """
        text = self.cbResultsIDName.currentText()
        if len(text) > 0:
            parcel_id = int(self.cbResultsIDName.currentText().split(" - ")[0])
            return parcel_id

    def set_current_parcel(self, parcel_id):
        """
         Sets the current active parcel for the given ID.
        :param parcel_id: parcel's ID (integer)
        """
        print("set_current_parcel({0})".format(parcel_id))

        if parcel_id is not None:
            for i in range(self.cbResultsIDName.count()):
                cur_pid = int(self.cbResultsIDName.itemText(i).split(" - ")[0])
                if cur_pid == parcel_id:
                    self.cbResultsIDName.setCurrentIndex(i)

                    self.parcel_id_to_set = None # reset

    def update_parcel_data(self, api_key, base_url, parcel_id):
        """
         Updates the data (detail attribute data) for the given parcel id from the API if necessary
         and zooms to the parcel's geometry.

        :param api_key: API key for agknow service (string)
        :param base_url: base URL for the agknow service (string)
        :param parcel_id: parcel's ID (integer)
        """
        # wait cursor
        QApplication.setOverrideCursor(Qt.WaitCursor)

        print("update_parcel_data()")

        try:
            # download parcel attribute data if not present
            if parcel_id not in self.parcel_ids:

                # sync download of parcel's detail data, because it is not worth it to start a worker for this
                # read geom as WKT
                attributes, geom_wkt = self.utils.get_parcel_detail_data(base_url, api_key, parcel_id)

                geom = QgsGeometry.fromWkt(geom_wkt)

                # src epsg is always 4326 because it is the source epsg of the agknow API v3
                tgeom = self.utils.transform_geom(geom, src_epsg_code=4326,
                                                  dst_epsg_code=self.get_layer_epsg(self.parcelLyr))

                self.utils.add_feature(tgeom, attributes, self.parcelLyr, self.parcel_ids)

                # do the transform for the zooming to the current project's srs if necessary
                if self.get_current_project_epsg() != self.get_layer_epsg(self.parcelLyr):
                    tgeom = self.utils.transform_geom(tgeom, src_epsg_code=self.get_layer_epsg(self.parcelLyr),
                                                      dst_epsg_code=self.get_current_project_epsg())

                extent = tgeom.boundingBox()

                # preparation for images - init image group layer once per parcel
                self.init_group_layers(parcel_id, self.product)

                self.set_map_to_extent(extent)

                # slightly zoom out for nicer display
                self.iface.mapCanvas().zoomByFactor(1.1)

                # Bug in QGIS 3.4.x? sometimes QGIS draws an empty mapCanvas for the temporary layer
                # so force QGIS to refresh the mapcanvas
                self.iface.mapCanvas().clearCache()
                self.iface.mapCanvas().refresh()

            # otherwise just hop to the selected one
            else:
                self.zoom_to_parcel(parcel_id)

        except Exception as e:
            QgsMessageLog.logMessage("Error downloading parcel's detail data! parcel id: {0}".format(parcel_id),
                                     "agknow", Qgis.Critical)
            QgsMessageLog.logMessage("update_parcel_data(): {0}".format(e), "agknow", Qgis.Critical)

        finally:
            # restore cursor
            QApplication.restoreOverrideCursor()

    def update_parcel_images(self, api_key, base_url, parcel_ids):
        """
         Updates the images for the given list of parcel ids if necessary.

        DO NOT use in a for loop because it will start an asynchronous worker!

        - checks for raster ids in self.rasters to prevent duplicate download
          {parcel_id + product + data_source : [raster_ids]}

        :param api_key: API key for agknow service (string)
        :param base_url: base URL for the agknow service (string)
        :param parcel_ids: list of parcel's ID (list of integers)
        """
        print("update_parcel_images()")
        # wait cursor
        QApplication.setOverrideCursor(Qt.WaitCursor)

        self.read_agknow_settings()

        # image download
        if self.chkBoxDownloadImg.isChecked():

            for parcel_id in parcel_ids:

                # unique ID for parcel, product, data_source and img_format
                raster_group_id = "{0}_{1}_{2}_{3}".format(parcel_id, self.product, self.data_source,
                                                           self.settings["image_format"])

                # in checks for keys in dictionary
                if raster_group_id not in self.rasters:
                    print("raster_group_id: {0} not found - downloading from server..".format(raster_group_id))
                    QgsMessageLog.logMessage("raster_group_id: {0} not found - downloading from server..".format(raster_group_id), "agknow",
                                             Qgis.Info)

                    # remove all images in toc for selected product (mind the whitespace again!)
                    self.clear_images_toc(parcel_id, self.product + " ", self.data_source)

                else:
                    # remove from worker load
                    parcel_ids.remove(parcel_id)

                    QgsMessageLog.logMessage("raster_group_id: {0} exists already!".format(raster_group_id), "agknow",
                                             Qgis.Info)

            # only start worker if we have some load
            if len(parcel_ids) > 0:
                ## async with worker
                api_key = self.tbAPIKey.text()
                host_url = self.tbHostURL.text()
                
                base_url = host_url + self.api_version

                self.init_progressBar()
                #print("update_parcel_images() - return")
                #return

                kwargs = {"base_url": base_url, "product_id": self.product, "parcel_ids": parcel_ids,
                          "data_source": self.data_source, "ssl_verify": True, "api_key": api_key,
                          "img_format": self.settings["image_format"],
                          "project_epsg": self.get_current_project_epsg(),
                          "api_version": self.api_version}

                self.startWorker(_runMethod="get_images",
                                 _finishedEvtMethod="get_images_finished",
                                 _errorEvtMethod="get_images_error",
                                 **kwargs)
            else:

                raster_group_id = "{0}_{1}_{2}_{3}".format(self.get_current_parcel_id(), self.product, self.data_source,
                                                           self.settings["image_format"])
                # notify change on slot for refresh of timeslider
                self.imagesReloaded.emit(self.rasters[raster_group_id])

                self.deactivate_connecting_state()

        else:
            raster_group_id = "{0}_{1}_{2}_{3}".format(self.get_current_parcel_id(), self.product, self.data_source,
                                                       self.settings["image_format"])
            # notify change on slot for refresh of timeslider
            try:
                self.imagesReloaded.emit(self.rasters[raster_group_id])
            except KeyError as e:
                QgsMessageLog.logMessage("raster_group_id: {0} not found!".format(raster_group_id), "agknow",
                                         Qgis.Warning)

            self.deactivate_connecting_state()

    def update_parcel_data_and_images(self):
        """
         Updates the current selected parcel's detail data and images. Convenience function for external call
        """
        print("update_parcel_data_and_images()")

        # catch empty combobox
        if len(self.cbResultsIDName.currentText()) < 1:
            return

        parcel_id = self.get_current_parcel_id()
        api_key = self.tbAPIKey.text()
        host_url = self.tbHostURL.text()
        
        base_url = host_url + self.api_version

        self.update_parcel_data(api_key, base_url, parcel_id)

        self.toggle_parcels_toc(parcel_id)

        self.update_parcel_images(api_key, base_url, [parcel_id])

    def toggle_parcels_toc(self, parcel_id):
        """
         Toggles off all other parcel groups except the one with the given parcel_id
         and collapse them.
        :param parcel_id: the parcel's ID (integer)
        """
        root = QgsProject.instance().layerTreeRoot()

        for p in self.parcel_ids:

            parcel_group = root.findGroup("parcel id: {0}".format(p))

            if parcel_group is not None:
                if p == parcel_id:
                    parcel_group.setItemVisibilityChecked(Qt.Checked)
                    parcel_group.setExpanded(True)
                else:
                    parcel_group.setItemVisibilityChecked(Qt.Unchecked)
                    parcel_group.setExpanded(False)

    def clear_images_toc(self, parcel_id, product_id, data_source):
        """
         Toggles off all other parcel groups except the one with the given parcel_id
         and collapse them.

        :param parcel_id: the parcel's ID (integer)
        :param product_id: product id: visible, vitality, variations, etc. (string)
        :param data_source: landsat-8 or sentinel-2 (string)
        """
        root = QgsProject.instance().layerTreeRoot()

        parcel_group = root.findGroup("parcel id: {0}".format(parcel_id))

        if parcel_group is not None:
            product_group = parcel_group.findGroup(product_id)

            if product_group is not None:
                data_source_group = product_group.findGroup(data_source)

                if data_source_group is not None:
                    # clear all child nodes (= images per date)
                    data_source_group.removeAllChildren()

    def reset_toc(self):
        """
         Removes all images from the images group of the TOC.
        """
        root = QgsProject.instance().layerTreeRoot()
        image_group = root.findGroup("images")

        if image_group is not None:
            image_group.removeAllChildren()

    def freeze_image_format_to_tiff(self):
        """
         Freezes the radio button to the image format tiff.
        """
        self.rdBtnImgOptTiff.toggle()
        self.grBoxImgFormat.setEnabled(False)

    def freeze_image_format_to_png(self):
        """
         Freezes the radio button to the image format png.
        """
        self.rdBtnImgOptPNG.toggle()
        self.grBoxImgFormat.setEnabled(False)

    def enable_image_format(self):
        """
         Enables the radio button for the image format.
        """
        self.grBoxImgFormat.setEnabled(True)

    # should be called in GUI thread because it manipulates GUI elements
    def add_image_toc(self, mmap_name, lyrName, parcel_id, product_id, data_source):
        """
         Adds the given image layer to the relevant group in the TOC. Honors the in_memory flag of checkbox "chkBoxSaveImg"

        :param mmap_name: GDAL memory map name (string)
        :param lyrName: name of the layer (string)
        :param parcel_id: parcel's ID (integer)
        :param product_id: product id: visible, vitality, variations, etc. (string)
        :param data_source: landsat-8 or sentinel-2 (string)

        """
        # layername must be string! integer does not work!
        if self.chkBoxSaveImg.isChecked():
            # save to disk
            # lyr_name = "{0}|{1}|{2}|{3}".format(r["product"], r["date"], r["raster_id"], r["source"])
            product, date, raster_id, source = lyrName.split('|')
            print(product, date, raster_id, source)

            out_path = os.path.join(self.plugin_dir, "cache", "parcels", str(parcel_id), source, product, str(raster_id))

            out_path = "{0}_{1}.{2}".format(out_path, date, self.settings["image_format"])

            out_path_subdir = os.path.dirname(out_path)

            if not os.path.exists(out_path_subdir):
                os.makedirs(out_path_subdir, exist_ok=True)

            print("Exporting to {0}..".format(out_path))
            self.utils.exportGDALraster(mmap_name, out_path)

            # memory clean up
            gdal.Unlink(mmap_name)

            rlyr = QgsRasterLayer(out_path, str(lyrName))

        else:
            rlyr = QgsRasterLayer(mmap_name, str(lyrName))

        # add to registry without showing up on TOC
        mapLyr = QgsProject.instance().addMapLayer(rlyr, addToLegend=False)

        # add to product group
        root = QgsProject.instance().layerTreeRoot()

        product_group = root.findGroup("parcel id: {0}".format(parcel_id)).findGroup(product_id + " ").findGroup(
            data_source)

        # add map layer to this group
        product_group.addLayer(mapLyr)

        return rlyr.source()

    def init_group_layers(self, parcel_id, product_id):
        """
         Initializes the group layer structure of agknow for the given parcel ID and product.

        :param parcel_id: parcel's ID (integer)
        :param product_id: product id: visible, vitality, variations, etc. (string)
        """
        # create or get parcel_group
        parcel_group = self.init_base_layers(parcel_id)

        # add subgroups per product and data source
        # don't know why, but vitality must not be simple 'vitality' but has to have
        # an additional character (e.g. whitespace)
        p_group = parcel_group.findGroup(product_id + u" ")

        if p_group is None:
            p_group = parcel_group.addGroup(product_id + u" ")

            if product_id in [u"visible", u"vitality", u"variations"]:

                ds_group = p_group.findGroup(u"landsat8")
                if ds_group is None:
                    p_group.addGroup(u"landsat8")
                else:
                    self.clear_images_toc(parcel_id, product_id, u"landsat8")

                ds_group = p_group.findGroup(u"sentinel2")
                if ds_group is None:
                    p_group.addGroup(u"sentinel2")
                else:
                    self.clear_images_toc(parcel_id, product_id, u"sentinel2")

            else:
                ds_group = p_group.findGroup(u"sentinel2")
                if ds_group is None:
                    p_group.addGroup(u"sentinel2")
                else:
                    self.clear_images_toc(parcel_id, product_id, u"sentinel2")

    def init_base_layers(self, parcel_id):
        """
         Initializes the base agknow layers in the TOC.

        :param parcel_id: parcel's ID (integer)
        :return parcel_group: group layer of the parcel's ID (QgsLayerTreeGroup)
         
        """
        # root node
        root = QgsProject.instance().layerTreeRoot()

        # parcels and images are loaded at init of agknow plugin, so they must be present
        images_group = root.findGroup(u"images")

        # add new parcel group to images_group if not present
        parcel_group = images_group.findGroup("parcel id: {0}".format(parcel_id))

        if parcel_group is None:
            parcel_group = images_group.addGroup("parcel id: {0}".format(parcel_id))

        return parcel_group

    def set_map_to_center(self, x, y):
        """
         Center the map to the given coordinates.

        :param x: X-Coordinate (double)
        :param y: Y-Coordinate (double)
        """
        self.canvas.setCenter(QgsPoint(x, y))
        self.canvas.refresh()

    def set_map_to_extent(self, bbox):
        """
         Sets the current extent of the map to the given bounding box.

        :param bbox: Bounding Box (QgsRectangle)
        """
        self.canvas.setExtent(bbox)
        self.canvas.refresh()

    def zoom_to_parcel(self, parcel_id):
        """
         Zooms to the given parcel_id.

        :param parcel_id: (int)
        """
        print("zoom_to_parcel({0})".format(parcel_id))

        request = QgsFeatureRequest(
            QgsExpression("parcel_id = {0}".format(parcel_id)))  # .setFilterFid(parcel_id)
        request.setFlags(QgsFeatureRequest.NoGeometry)

        # there may be an empty feature request, if event fires too early
        try:
            feature = next(self.parcelLyr.getFeatures(request))
        except:
            QgsMessageLog.logMessage("Feature {0} not found".format(parcel_id),  "agknow", Qgis.Warning)
            return

        tgeom = feature.geometry()

        # do the transform for the zooming to the current project's srs if necessary
        if self.get_current_project_epsg() != self.get_layer_epsg(self.parcelLyr):
            tgeom = self.utils.transform_geom(feature.geometry(),
                                              src_epsg_code=self.get_layer_epsg(self.parcelLyr),
                                              dst_epsg_code=self.get_current_project_epsg())
        extent = tgeom.boundingBox()

        self.set_map_to_extent(extent)

        # slightly zoom out for nicer display
        self.iface.mapCanvas().zoomByFactor(1.1)


    def remove_all_features(self, lyr):
        """
         Removes all feature ot the given QgsVectorLayer.

        :param lyr: (QgsVectorLayer)
        """
        lyr.startEditing()

        features = lyr.getFeatures()
        delFeatures = []
        for feat in features:
            delFeatures.append(feat.id())

        lyr.dataProvider().deleteFeatures(delFeatures)
        lyr.commitChanges()

    def set_layer_style(self, lyr, style_path):
        """
         Sets the style to a QgsMapLayer from the given path to the style file.

        :param lyr: (QgsMapLayer)
        :param style_path: path to QGIS style file (string)
        """
        lyr.loadNamedStyle(style_path)

    # Region asynchronous
    #
    def startWorker(self, _runMethod, _finishedEvtMethod, _errorEvtMethod=None, **kwargs):
        """
        Generic worker starter.
        Pass the processing function for the thread and the method for the \n
        finished event as strings.

        :param _runMethod: name of method to call in the worker class
        :param _finishedEvtMethod: name of method of the caller class, that will be called when the task is finished.
        :param _errorEvtMethod: optional name of method of the caller class, that will be called when the task has an error.
        :param kwargs: Keyword arguments
        """
        worker = Worker(**kwargs)
        thread = QThread()
        worker.moveToThread(thread)
        # getattr() can call functions via string

        worker.progress.connect(self.progress.setValue)
        worker.status.connect(self.iface.mainWindow().statusBar().showMessage)
        worker.finished.connect(getattr(self, _finishedEvtMethod))

        if _errorEvtMethod is not None:
            worker.error.connect(getattr(self, _errorEvtMethod))

        thread.started.connect(getattr(worker, _runMethod))
        # self.worker.set_data(**kwargs)
        thread.start()

        # hold a reference in the class instance so the the objects are not being garbage collected too early
        self.thread = thread
        self.worker = worker


    def cleanup_threading(self):
        """
         Cleans up all thread/worker issues after the work is done.
        """

        print("cleanup_threading()")
        # clean up the worker and thread
        # clean up the worker and thread uncessary? thread was already garbage collected
        #self.worker.deleteLater()
        self.thread.quit()
        self.thread.wait()
        self.thread.deleteLater()
        # self.thread = self.worker = None

    def handle_connect_result(self, result):
        """
         Handles the further processing of the result object of an asynchronous worker.
         May start another async worker process.

        :param result: result of a call to the agknow API. (dictionary)
        """
        print("handle_connect_result() - {0}".format(self.settings["parcel_download_mode"]))

        if self.settings["parcel_download_mode"] == "one-by-one":

            # fill combobox only with the parcel name and id
            # this will also trigger the cbResultsIDName_currentIndexChanged event
            # in which the download of the images happen if "download image" is active
            # and data is not already existent
            # disconnect the event listener temporary
            self.cbResultsIDName.currentIndexChanged.disconnect(self.cbResultsIDName_currentIndexChanged)

            for item in result["content"]:
                self.cbResultsIDName.addItem(u"{0} - {1}".format(item["parcel_id"], item["name"]))

            # connect the event listener again
            self.cbResultsIDName.currentIndexChanged.connect(self.cbResultsIDName_currentIndexChanged)

            self.iface.messageBar().clearWidgets()
            self.iface.messageBar().pushMessage("Success", "Successfully downloaded base parcel data!",
                                                level=Qgis.Success, duration=1)

            QgsMessageLog.logMessage("Successfully downloaded base parcel data.", "agknow",
                                     Qgis.Info)

            self.btnRefresh.setEnabled(True)

            if self.parcel_id_to_set is not None:
                # trigger the change event manually now to download the detail data and images per parcel
                # calls self.cbResultsIDName_currentIndexChanged() through selecting the given parcel_id
                self.set_current_parcel(self.parcel_id_to_set)
            else:
                # trigger the change event manually now to download the detail data and images per parcel
                self.cbResultsIDName_currentIndexChanged()

        else:  # download all details of the parcels and populate the combobox afterwards

            api_key = self.tbAPIKey.text()
            host_url = self.tbHostURL.text()
            

            base_url = host_url + self.api_version
            params = "/parcels/?key=" + api_key

            self.init_progressBar()

            self.iface.messageBar().pushMessage("Info", "Loading all parcel detail data at once may take a while..",
                                                level=Qgis.Info, duration=1)

            QgsMessageLog.logMessage("Loading all parcel detail data at once may take a while..", "agknow",
                                     Qgis.Info)

            parcel_ids = []
            for item in result["content"]:
                parcel_ids.append(item["parcel_id"])

            # async with worker
            kwargs = {"base_url": base_url, "ssl_verify": False, "parcel_ids": parcel_ids,
                      "api_key": api_key, "parcelLyr": self.parcelLyr, "project_epsg": self.get_current_project_epsg(),
                      "api_version": self.api_version}

            self.startWorker(_runMethod="get_parcels_detail_data",
                             _finishedEvtMethod="get_parcels_detail_data_finished",
                             _errorEvtMethod="get_parcels_detail_data_error",
                             **kwargs)

    # slot with return type
    @pyqtSlot(object)
    def get_parcel_base_data_finished(self, ret):
        """
         Event handler for the finished event of the get_parcel_base_data worker.

        :param ret: result of a call to the agknow API (JSON string)
        """
        print("get_parcel_base_data_finished()")

        # important! cleanup first before starting another thread
        self.cleanup_threading()

        if ret is not None:

            result = json.loads(ret)
            print(result)
            # check for correct api key
            if result["content"] == "key is not authorized":
                self.iface.messageBar().clearWidgets()
                self.iface.messageBar().pushMessage('API key is not authorized!',
                                                    level=Qgis.Critical,
                                                    duration=3)
                QgsMessageLog.logMessage('API key is not authorized!', "agknow",
                                         Qgis.Critical)
                self.deactivate_connecting_state()
                self.settings["connected"] = False
                self.show_disconnected_state()

                return
            # maybe API KEY is valid, but has no parcels
            elif len(result["content"]) == 0:
                self.iface.messageBar().clearWidgets()
                self.iface.messageBar().pushMessage("Warning", "No parcels found for this API Key!",
                                                    level=Qgis.Warning, duration=2)
                QgsMessageLog.logMessage("No parcels found for this API Key!", "agknow",
                                         Qgis.Warning)
                # no parcels to show - but we may register new ones!
                self.deactivate_connecting_state()
                self.settings["connected"] = True
                self.grBoxLayerSettings.setEnabled(self.settings["connected"])

                return
            else:
                self.settings["connected"] = True
                self.show_connected_state()

                # process the result
                # maybe sync or async
                self.handle_connect_result(result)

        else:
            # notify the user that something went wrong
            self.iface.messageBar().clearWidgets()
            self.iface.messageBar().pushMessage('Something went wrong! See the message log for more information.',
                                                level=Qgis.Critical,
                                                duration=3)

            QgsMessageLog.logMessage("get_parcel_base_data_finished(): return of async was None!", "agknow",
                                     Qgis.Critical)

            self.deactivate_connecting_state()
            self.settings["connected"] = False
            self.show_disconnected_state()

    def show_connected_state(self):
        """
         Shows connected state in the GUI.
        """
        self.rdBtnParcelDownloadAll.setEnabled(False)
        self.rdBtnParcelDownloadOne.setEnabled(False)
        self.btnConnect.setText("Disconnect")
        self.tbHostURL.setEnabled(False)
        self.tbAPIKey.setEnabled(False)
        self.cbAPIVersion.setEnabled(False)

    def show_disconnected_state(self):
        """
         Shows disconnected state in the GUI.
        """
        self.rdBtnParcelDownloadAll.setEnabled(True)
        self.rdBtnParcelDownloadOne.setEnabled(True)
        self.btnConnect.setText("Connect")
        self.tbHostURL.setEnabled(True)
        self.tbAPIKey.setEnabled(True)
        self.cbAPIVersion.setEnabled(True)

    def deactivate_connecting_state(self):
        """
         Restores the state for relevant GUI elements after connecting.
        """
        # restore cursor
        QApplication.restoreOverrideCursor()
        self.grBoxDataSource.setEnabled(True)
        self.grBoxParcelDownloadSettings.setEnabled(True)
        self.grBoxResults.setEnabled(True)
        self.btnConnect.setEnabled(True)
        self.btnRefresh.setEnabled(self.settings["connected"])
        self.grBoxLayerSettings.setEnabled(self.settings["connected"])
        #self.cbAPIVersion.setEnabled(self.settings["connected"])

    def activate_connecting_state(self):
        """
         Activates the state for relevant GUI elements while connecting.
        """
        # restore cursor
        QApplication.restoreOverrideCursor()
        self.grBoxDataSource.setEnabled(False)
        self.grBoxParcelDownloadSettings.setEnabled(False)
        self.grBoxResults.setEnabled(False)
        self.btnConnect.setEnabled(False)
        self.btnRefresh.setEnabled(False)
        self.grBoxLayerSettings.setEnabled(False)
        #self.cbAPIVersion.setEnabled(False)

    @pyqtSlot(str)
    def get_parcel_base_data_error(self, ret):
        """
         Event handler for the error event of the get_parcel_base_data worker.

        :param ret: traceback of the error (string)
        """
        print("get_parcel_base_data_error()")

        # important! cleanup first before starting another thread
        self.cleanup_threading()

        # notify the user that something went wrong
        self.iface.messageBar().pushMessage("Something went wrong! See the message log for more information.",
                                            level=Qgis.Critical,
                                            duration=3)
        if ret is not None:
            QgsMessageLog.logMessage("get_parcel_base_data_error(): {0}".format(ret), "agknow",
                                     Qgis.Warning)
        else:
            QgsMessageLog.logMessage("get_parcel_base_data_error(): return of async was None!", "agknow",
                                     Qgis.Critical)

        self.deactivate_connecting_state()


    # slot with return type
    @pyqtSlot(object)
    def get_parcels_detail_data_finished(self, ret):
        """
         Event handler for the finished event of the get_parcels_detail_data worker.

        :param ret: result of a call to the agknow API (JSON string)
        """
        print("get_parcels_detail_data_finished()")

        # important! cleanup first before starting another thread
        self.cleanup_threading()

        if ret is not None:

            self.set_map_to_extent(self.parcelLyr.extent())

            self.parcel_ids, parcel_ids_names = ret

            # maybe API KEY is valid, but has no parcels
            if len(self.parcel_ids) == 0:
                self.deactivate_connecting_state()
                self.iface.messageBar().pushMessage("Warning", "No parcels found for this API Key!",
                                                    level=Qgis.Warning, duration=2)
                return

            # IMPORTANT - deactivate the changed event for filling the combobox
            # because otherwise there are interfering threads (currentIndexChanged Event will also
            # call update_parcel_images(), but we call it here explicitely

            # disconnect the event listener temporary
            self.cbResultsIDName.currentIndexChanged.disconnect(self.cbResultsIDName_currentIndexChanged)

            for item in list(parcel_ids_names):
                self.cbResultsIDName.addItem(item)

            # connect the event listener again
            self.cbResultsIDName.currentIndexChanged.connect(self.cbResultsIDName_currentIndexChanged)

            # init group layers
            for p in self.parcel_ids:
                self.init_group_layers(p, self.product)

            # toggle parcels in toc except first
            self.toggle_parcels_toc(self.parcel_ids[0])

            self.iface.messageBar().pushMessage("Success", "Successfully downloaded parcels detail data!",
                                                level=Qgis.Success, duration=1)

            QgsMessageLog.logMessage("Successfully downloaded parcels detail data.", "agknow", Qgis.Info)

            try:
                if self.chkBoxDownloadImg.isChecked():
                    QgsMessageLog.logMessage("Downloading all parcel images..", "agknow", Qgis.Info)

                    api_key = self.tbAPIKey.text()
                    host_url = self.tbHostURL.text()
                    
                    base_url = host_url + self.api_version

                    # should be 1 thread per Core at least to download the data in parallel
                    # but for the first draw just put all the work into another thread
                    # calls async worker!
                    self.update_parcel_images(api_key, base_url, self.parcel_ids)

                else:
                    if self.parcel_id_to_set is not None:
                        # trigger the change event manually now to download the detail data and images per parcel
                        # calls self.cbResultsIDName_currentIndexChanged() through selecting the given parcel_id
                        self.set_current_parcel(self.parcel_id_to_set)
                    else:
                        # zoom to first parcel
                        self.zoom_to_parcel(self.get_current_parcel_id())

                    self.deactivate_connecting_state()

            except Exception as e:
                self.iface.messageBar().pushMessage('Something went wrong! See the message log for more information.',
                                                    level=Qgis.Critical,
                                                    duration=3)

                QgsMessageLog.logMessage("Error downloading all parcel images..", "agknow", Qgis.Warning)

                QgsMessageLog.logMessage("get_parcels_detail_data_finished(): {0}".format(e), "agknow",
                                         Qgis.Warning)

                self.deactivate_connecting_state()

        else:
            # notify the user that something went wrong
            self.iface.messageBar().pushMessage('Something went wrong! See the message log for more information.',
                                                level=Qgis.Critical,
                                                duration=3)

            QgsMessageLog.logMessage("get_parcels_detail_data_finished(): return of async was None!", "agknow",
                                     Qgis.Critical)

            self.deactivate_connecting_state()


    # slot with return type
    @pyqtSlot(str)
    def get_parcels_detail_data_error(self, ret):
        """
         Event handler for the error event of the get_parcels_detail_data worker.

        :param ret: traceback of the error (string)
        """
        print("get_parcels_detail_data_error()")

        # important! cleanup first before starting another thread
        self.cleanup_threading()

        if ret is not None:

            # notify the user that something went wrong
            self.iface.messageBar().pushMessage('Something went wrong! See the message log for more information.',
                                                level=Qgis.Critical,
                                                duration=3)

            QgsMessageLog.logMessage("get_parcels_detail_data_error(): {0}".format(ret), "agknow",
                                     Qgis.Warning)
        else:
            QgsMessageLog.logMessage("get_parcels_detail_data_error(): return of async was None!", "agknow",
                                     Qgis.Critical)

        self.deactivate_connecting_state()


    @pyqtSlot(object)
    def get_images_finished(self, ret):
        """
         Event handler for the finished event of the get_images worker.

        :param ret: dict {raster_group_id, raster list }
        """
        print("get_images_finished()")

        # important! cleanup first before starting another thread
        self.cleanup_threading()

        if ret is not None:

            for raster_group_id in ret.keys():

                QgsMessageLog.logMessage("raster_group_id: {0}".format(raster_group_id), "agknow",
                                         Qgis.Info)

                rasters = ret[raster_group_id] # dict {raster_group_id: rasters}

                QgsMessageLog.logMessage("Successfully downloaded images!", "agknow", Qgis.Info)

                self.rasters[raster_group_id] = rasters

                # add all rasters to the GUI
                new_rasters = []
                for r in rasters:
                    try:
                        # with date and raster ID as layername
                        lyr_name = "{0}|{1}|{2}|{3}".format(r["product"], r["date"], r["raster_id"], r["source"])

                        file_path = self.add_image_toc(r["mmap_name"], lyr_name, r["parcel_id"],
                                           r["product"], r["source"])

                        # update raster dictionary's path
                        r["mmap_name"] = file_path
                        new_rasters.append(r)

                    except Exception as e:
                        QgsMessageLog.logMessage("get_images_finished(): Error adding image to TOC", "agknow",
                                                 Qgis.Warning)
                        QgsMessageLog.logMessage("{0}".format(e), "agknow",
                                                 Qgis.Warning)

                # save updated rasters
                rasters = new_rasters
                self.rasters[raster_group_id] = rasters

                # notify change on slot
                self.imagesReloaded.emit(rasters)

            if self.parcel_id_to_set is not None:
                # trigger the change event manually now to download the detail data and images per parcel
                # calls self.cbResultsIDName_currentIndexChanged() through selecting the given parcel_id
                self.set_current_parcel(self.parcel_id_to_set)

            # zoom to first parcel
            print("get_images_finished() - zooming to parcel..")
            self.zoom_to_parcel(self.get_current_parcel_id())

            self.deactivate_connecting_state()

        else:
            QgsMessageLog.logMessage("get_images_finished(): return of async was None!", "agknow",
                                     Qgis.Critical)

        self.deactivate_connecting_state()
        self.btnRefresh.setEnabled(self.settings["connected"])
        self.grBoxLayerSettings.setEnabled(self.settings["connected"])

    @pyqtSlot(str)
    def get_images_error(self, ret):
        """
         Event handler for the error event of the get_images worker.

        :param ret: traceback of the error (string)
        """
        print("get_images_error()")

        # important! cleanup first before starting another thread
        self.cleanup_threading()

        if ret is not None:
            # notify the user that something went wrong
            self.iface.messageBar().pushMessage('Something went wrong! See the message log for more information.',
                                                level=Qgis.Critical,
                                                duration=2)
            QgsMessageLog.logMessage("get_images_error(): {0}".format(ret), "agknow",
                                     Qgis.Warning)

        else:
            QgsMessageLog.logMessage("get_images_error(): return of async was None!", "agknow",
                                     Qgis.Warning)

        self.deactivate_connecting_state()
        self.btnRefresh.setEnabled(self.settings["connected"])
        self.grBoxLayerSettings.setEnabled(self.settings["connected"])

    @pyqtSlot(object)
    def register_feature_finished(self, ret):
        """
         Event handler for the error event of the register_feature_finished worker.

        :param ret: JSON string from the agknow API
        """
        print("register_feature_finished()")

        # important! cleanup first before starting another thread
        self.cleanup_threading()

        if ret is not None:

            # Success APIv3:
            # {"errors": "", "messages": {"status": "Successfully created parcel"}, "id": 19}
            # Error on wrong geometry
            # {u'errors': u'Could not read geometry from WKT', u'id': None}

            # Success APIv4:
            # {"content": {"parcel_id": 12101, "crop": "test", "name": "test", "entity": "", "area": 8784.87509489059,
            #              "planting": "2021-03-01", "harvest": "2021-04-01",
            #              "geometry": "MULTIPOLYGON(((12.128731 48.57026,12.129391 48.570464,12.130901 48.569232,12.130137 48.569124,12.128731 48.57026)))",
            #              "promotion": false, "userdata": null},
            #  "messages": {"entity": "Warning: no entity name provided, left empty",
            #               "status": "Successfully created parcel"}}

            ret_dict = json.loads(ret)
            
            success = False
            if self.api_version.endswith("3"):
                if len(ret_dict["errors"]) == 0:
                    success = True
                    new_id = ret_dict["id"]
            elif self.api_version.endswith("4"):
                if "content" in ret_dict:
                    success = True
                    new_id = ret_dict["content"]["parcel_id"]

            if success is True:
                status = ret_dict["messages"]["status"]

                self.iface.messageBar().clearWidgets()
                self.iface.messageBar().pushMessage('Successfully registered feature with ID {0}'.format(new_id),
                                                level=Qgis.Success,
                                                duration=1.5)

                self.iface.mainWindow().statusBar().showMessage("{0}: {1}".format(status, new_id))

                QgsMessageLog.logMessage("register_feature_finished(): {0}".format("{0}: {1}".format(status, new_id)),
                                         "agknow",
                                         Qgis.Info)

                # TODO better design - don't call the whole chain for "all-at-once" it will update all data
                #  - only refresh the combobox with base data
                #  - only refresh the new parcel with image data

                # so set the mode back to one-by-one when registering
                # maybe changed only with disconnect / connect again
                self.rdBtnParcelDownloadOne.setChecked(True)
                self.settings["parcel_download_mode"] = "one-by-one"

                if self.settings["parcel_download_mode"] == "one-by-one":
                    # refresh parcels and select the new one?
                    self.connect()

                    # set the new id here because the self.connect() method calls a async worker chain
                    # and it would be too much work to pass the parcel id through the whole chain.
                    self.parcel_id_to_set = new_id

            else:
                # error API v4 sample:
                # {"error":"Usage status error","detail":"maximum amount of hectares registered"}
                status = ""
                if self.api_version.endswith("4"):
                    status = f"{ret_dict['error']}: {ret_dict['detail']}"

                if self.api_version.endswith("3"):
                    status = ret_dict["errors"]

                self.iface.messageBar().clearWidgets()
                self.iface.messageBar().pushMessage('Something went wrong! {0} See the message log for more information.'.format(status),
                                                level=Qgis.Critical,
                                                duration=5)
                self.iface.mainWindow().statusBar().showMessage("ERROR - {0}!".format(status))

                QgsMessageLog.logMessage("ERROR - register_feature_finished(): {0}!".format("{0}".format(status)),
                                         "agknow",
                                         Qgis.Critical)

        else:
            QgsMessageLog.logMessage("register_feature_finished(): return of async was None!", "agknow",
                                     Qgis.Warning)

    @pyqtSlot(str)
    def register_feature_error(self, ret):
        """
         Event handler for the error event of the register_feature_error worker.

        :param ret: traceback of the error (string)
        """
        print("register_feature_error()")

        # important! cleanup first before starting another thread
        self.cleanup_threading()

        if ret is not None:
            # notify the user that something went wrong
            self.iface.messageBar().pushMessage(
                'Something went wrong! {0} See the message log for more information.',
                level=Qgis.Critical,
                duration=5)

            QgsMessageLog.logMessage("register_feature_error(): {0}".format(ret), "agknow",
                                     Qgis.Warning)

        else:
            QgsMessageLog.logMessage("register_feature_error(): return of async was None!", "agknow",
                                     Qgis.Warning)
