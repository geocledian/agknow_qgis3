# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Agknow
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
from __future__ import absolute_import

from qgis.PyQt import QtCore
from qgis.PyQt.QtCore import pyqtSlot, pyqtSignal

from qgis.core import QgsGeometry, QgsMessageLog, Qgis

import requests, json

from . import agknow_utils

# Multithreading for GUI responsiveness
# Adopted from
# https://gis.stackexchange.com/questions/64831/how-do-i-prevent-qgis-from-being-detected-as-not-responding-when-running-a-hea/64928#64928
class Worker(QtCore.QObject):
    """
     Worker Class for seperating background work from the GUI thread of QGIS.
    """
    progress = QtCore.pyqtSignal(int)
    status = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    # return type is any Python Object
    finished = QtCore.pyqtSignal(object)

    def __init__(self, **kwargs):
        """
         Constructor

        :param kwargs: The Worker Class has keyword arguments in the constructor in order to pass data to it.
                    That may seem quirky but apparently is the only way to pass (different) data to the instance of the class.
        """

        QtCore.QObject.__init__(self)

        self.api_version = kwargs.get("api_version")

        self.utils = agknow_utils.AgknowUtils(self.api_version)

        self.processed = 0
        self.percentage = 0
        self.abort = False
        self.feature_count = 1

        self.ssl_verify = True

        self.initial_project_epsg = 4326

        # input data to be filled
        if "base_url" in kwargs:
            self.base_url = kwargs["base_url"]
        if "params" in kwargs:
            self.params = kwargs["params"]
        if "ssl_verify" in kwargs:
            self.ssl_verify = kwargs["ssl_verify"]
        if "parcel_ids" in kwargs:
            self.parcel_ids = kwargs["parcel_ids"]
        if "parcelLyr" in kwargs:
            self.parcelLyr = kwargs["parcelLyr"]
        if "api_key" in kwargs:
            self.api_key = kwargs["api_key"]
        if "project_epsg" in kwargs:
            self.initial_project_epsg = int(kwargs["project_epsg"])

        # for image download
        if "parcel_id" in kwargs:
            self.parcel_id = kwargs["parcel_id"]
        if "product_id" in kwargs:
            self.product_id = kwargs["product_id"]
        if "data_source" in kwargs:
            self.data_source = kwargs["data_source"]
        if "img_format" in kwargs:
            self.img_format = kwargs["img_format"]

        # for register feature
        if "feature_to_register" in kwargs:
            self.feature_to_register = kwargs["feature_to_register"]
        if "geometry_epsg" in kwargs:
            self.geometry_epsg = kwargs["geometry_epsg"]

    @pyqtSlot()
    def http_get(self):
        """Performs a HTTP GET request with the given base_url and optional URL parameters. Honors also a global boolean
        SSL_VERIFY to override ssl_verify.

        """
        url = self.base_url + self.params
        self.status.emit("Processing GET request from URL {0}".format(url))

        try:
            # timeout 10 seconds
            resp = requests.get(url, verify=self.ssl_verify, timeout=10.0)

            if resp.status_code == 200:

                # return on finished slot
                self.finished.emit(resp.text)
            else:
                self.error.emit(str(resp.status_code))
                self.error.emit(resp.text)
                self.finished.emit(None)

            self.status.emit('GET Request processed!')

        except requests.ConnectionError as e:
            import traceback
            self.error.emit(traceback.format_exc())
            # don't return exceptions? QGIS crashed
            #self.error.emit(e)
            self.finished.emit(None)

        except Exception as e:
            import traceback
            self.error.emit(traceback.format_exc())
            # don't return exceptions? QGIS crashed
            #self.error.emit(e)
            self.finished.emit(None)

    @pyqtSlot()
    def get_parcels_detail_data(self):
        """
         Gets parcel's base data like attributes and geometry, transform them to the desired SRS and add them to the
         parcel layer. Also it emits the status and percentage of completion.

         All data is fetched from the instance of the class.

        """
        self.status.emit("Getting all parcels base data..")

        self.feature_count = len(self.parcel_ids)

        self.parcelLyr.startEditing()

        parcel_ids = []
        parcel_ids_names = []
        for parcel_id in self.parcel_ids:

            try:
                attributes, geom_wkt = self.utils.get_parcel_detail_data(self.base_url, self.api_key, parcel_id)

                geom = QgsGeometry.fromWkt(geom_wkt)

                tgeom = self.utils.transform_geom(geom, src_epsg_code=4326, dst_epsg_code=self.initial_project_epsg)

                self.utils.add_feature(tgeom, attributes, self.parcelLyr, parcel_ids, parcel_ids_names)

                self.calculate_progress()

            except:
                import traceback
                self.error.emit(traceback.format_exc())
                self.finished.emit(None)

        self.parcelLyr.commitChanges()

        self.finished.emit([parcel_ids, parcel_ids_names])

        self.status.emit("Done!")

    @pyqtSlot()
    def get_images(self):
        """
         Gets parcel's image data, transform them to the desired SRS add them to the
         TOC. Also it emits the status and percentage of completion.

         All data is fetched from the instance of the class.
        """

        try:
            QgsMessageLog.logMessage("AgknowWorker - Downloading images..", "agknow", Qgis.Info)

            self.feature_count = len(self.parcel_ids)

            result = {}
            counter = 0

            for parcel_id in self.parcel_ids:

                self.status.emit("Downloading images: {0}/{1} parcels ready".format(counter, len(self.parcel_ids)))

                # unique ID for parcel, product, data_source and img_format
                raster_group_id = "{0}_{1}_{2}_{3}".format(parcel_id, self.product_id, self.data_source, self.img_format)

                rasters = self.utils.get_raster_list(self.base_url, self.api_key, parcel_id, self.product_id,
                                                     self.data_source)

                # show progress for all images for this parcel
                self.feature_count = len(rasters)

                failed_rasters = []

                for r in rasters:

                    raster_id = r["raster_id"]

                    #print("raster_id {0}".format(r["raster_id"]))
                    date = r["date"]

                    try:
                        mmap_name = self.utils.download_image(self.api_key, self.base_url, parcel_id, self.product_id,
                                                        raster_id, self.data_source, self.img_format, epsg=self.initial_project_epsg)

                        # add a new key to the dict with the memory map name of the downloaded raster
                        r["mmap_name"] = mmap_name

                        # show progress for all images for this parcel
                        self.calculate_progress()

                    # maybe image is corrupt or the scene has not the required bands for the index
                    except Exception as e:
                        QgsMessageLog.logMessage("AgknowWorker - Download of image {0} failed!".format(raster_id), "agknow", Qgis.Warning)
                        QgsMessageLog.logMessage("AgknowWorker\n - {0}".format(e.message), "agknow", Qgis.Warning)
                        #print("Download of image {0} failed!".format(raster_id))
                        #print(e.message)

                        # remove failed from raster list!
                        failed_rasters.append(r)

                result[raster_group_id] = rasters
                counter += 1

                #self.calculate_progress()

                for fr in failed_rasters:
                    rasters.remove(fr)

            # dict with all rasters per parcel_id
            self.finished.emit(result) #rasters))

        except Exception as e:

            import traceback
            self.error.emit(traceback.format_exc())
            # don't return exceptions? QGIS crashed
            #self.error.emit(e)
            self.finished.emit(None)

    @pyqtSlot()
    def register_feature(self):
        """
         Register feature in the agknow API.
        """
        try:
            QgsMessageLog.logMessage("AgknowWorker - Registering feature in ag|knowledge service..", "agknow", Qgis.Info)

            self.status.emit("Registering feature..")

            geom = QgsGeometry.fromWkt(self.feature_to_register["geometry"])

            # check for validity here
            if geom is None:
                self.error.emit("Geometry is not valid!")

                return

            tgeom = self.utils.transform_geom(geom, src_epsg_code=self.geometry_epsg, dst_epsg_code=4326)

            postdata = {"crop": self.feature_to_register["crop"],
                        "name": self.feature_to_register["name"],
                        "entity": self.feature_to_register["entity"],
                        "planting": self.feature_to_register["planting"],
                        "harvest": self.feature_to_register["harvest"],
                        "geometry": tgeom.asWkt().upper()
                        }

            #print(postdata)

            result = self.utils.sync_http_post(self.base_url, self.params, json.dumps(postdata))

            self.finished.emit(result)

        except Exception as e:

            import traceback
            self.error.emit(traceback.format_exc())
            # don't return exceptions? QGIS crashed
            #self.error.emit(e)

    @pyqtSlot()
    def calculate_progress(self):
        """
         Calculates the progress of the processed parcels.

         All data is fetched from the instance of the class.

        """
        self.processed = self.processed + 1
        percentage_new = (self.processed * 100) / self.feature_count
        if percentage_new > self.percentage:
            self.percentage = percentage_new
            self.progress.emit(self.percentage)



