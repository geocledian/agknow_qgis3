# -*- coding: utf-8 -*-
"""
/***************************************************************************
 AgknowUtils
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

from builtins import object
from qgis.core import QgsGeometry, QgsFeature, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
import requests, json

import gdal, osr
from uuid import uuid4

class AgknowUtils(object):
    """
     Utils class for the agknow plugin.
    """
    def __init__(self, api_version):
        self.api_version = api_version

    def add_feature(self, geom, attributes, lyr, parcel_ids, parcel_ids_names=[]):
        """
         Adds a QgsFeature (geometry and attributes) to the given QgsVectorLayer.
         parcel_ids and parcel_ids_names are manipulated inside this method.

        :param geom: The geometry for the feature (should be in the correct SRS of the layer - no checking here!
        :param attributes: dictionary of hard coded attributes for the layer - must fit the data model of the layer!
        :param lyr: QgsVectorLayer
        :param parcel_ids: list of parcel_ids; parcel_id is appended to it after the adding of the feature to the layer
        :param parcel_ids_names: list of parcel_ids and parcel names; parcel_id and parcel name
               are appended to it after the adding of the feature to the layer

        parcel_ids and parcel_ids_names are both used for the internal checking of already added parcels

        """
        feat = QgsFeature()
        feat.setId(attributes["parcel_id"])

        feat.setGeometry(geom)

        #
        row = [ attributes["parcel_id"], attributes["name"], attributes["entity"], attributes["crop"],
                attributes["startdate"], attributes["enddate"], attributes["planting"],attributes["harvest"],
                attributes["area"], attributes["apikey"], attributes["host"]
                ]

        feat.setAttributes(row)

        lyr.dataProvider().addFeatures([feat])

        parcel_ids.append(attributes["parcel_id"])
        parcel_ids_names.append(u"{0} - {1}".format(attributes["parcel_id"], attributes["name"]))

    def transform_geom(self, geom, src_epsg_code, dst_epsg_code):
        """
         Transforms the given QgsGeometry object with the given src and dest EPSG code parameters.

        :param geom: QgsGeometry object
        :param src_epsg_code: source EPSG Code
        :param dst_epsg_code: destination EPSG Code

        :return: transformed QgsGeometry object
        """

        if isinstance(src_epsg_code, type(1)) and isinstance(dst_epsg_code, type(1)):

            crsSrc = QgsCoordinateReferenceSystem.fromEpsgId(src_epsg_code)
            crsDest = QgsCoordinateReferenceSystem.fromEpsgId(dst_epsg_code)
            xform = QgsCoordinateTransform(crsSrc,
                                           crsDest,
                                           QgsProject.instance())

            geom.transform(xform)

            return geom

        else:
            return None

    def sync_http_get(self, base_url, params="", ssl_verify=True, return_raw=False):
        """
         Performs a HTTP GET request with the given base_url and optional URL parameters. Honors also a global boolean
        SSL_VERIFY to override ssl_verify.

        :param base_url: URL for the HTTP GET request
        :param params: URL parameters (e.g. ?key=kkk&entity=eee), optional
        :param ssl_verify: shall the host be verified according to its TLS certificate or not; default is True
        :param return_raw: returns get result of the GET request as raw binary or not (text); default is False so text is returned
        """
        url = base_url + params
        ## NO PRINTING TO CONSOLE in worker call!!

        #print(url)

        try:
            # timeout 5 seconds
            resp = requests.get(url, verify=ssl_verify, timeout=5.0)

            if resp.status_code == 200:

                if not return_raw:
                    return resp.text
                else:
                    return resp.content
            else:
                print(resp.status_code)
                print(resp.text)
                # API v4 won't return HTTP 200 on error
                if self.api_version.endswith("4"):
                    return resp.text

        except requests.ConnectionError as e:
            print(e)

    def sync_http_post(self, base_url, params="", postdata="", ssl_verify=True):
        """
         Performs a HTTP POST request with the given base_url and optional URL parameters. Honors also a global boolean
        SSL_VERIFY to override ssl_verify.

        :param base_url: URL for the HTTP GET request
        :param params: URL parameters (e.g. ?key=kkk&entity=eee), optional
        :param postdata: JSON String as POST data load, required
        :param ssl_verify: shall the host be verified according to its TLS certificate or not; default is True
        """
        #url = "https://vs3.geocledian.com/agknow/api/v3/parcels"

        # key as parameter
        url = base_url + params

        print("sync_http_post()")
        print("url: "+url)
        headers = {'Content-type': 'application/json'}
        try:
            print(json.dumps(postdata))
            # timeout 10 seconds
            resp = requests.post(url, data=postdata, headers=headers, verify=ssl_verify, timeout=10.0)

            if resp.status_code == 200:
                return resp.text
            else:
                print(resp.status_code)
                print(resp.text)
                # API v4 won't return HTTP 200 on error
                if self.api_version.endswith("4"):
                    return resp.text

        except ConnectionError as e:
            print(e)

    def get_parcel_detail_data(self, base_url, api_key, parcel_id):
        """
         Gets the detail parcel data from the given URL, API key and parcel id such as
         geometry as WKT and all attribute data of the parcel (crop, entity, harvest date, planting, etc.)
         from the agknow API.

        :param base_url: URL for the HTTP GET request
        :param api_key: API key for agknow
        :param parcel_id: parcel id

        :return: tuple of attribute dictionary and the geometry as WKT
        """
        params = "/parcels/{0}/?key={1}&geoformat=WKT".format(parcel_id, api_key)

        result = json.loads(self.sync_http_get(base_url, params))

        data = {}
        attributes = {}

        if self.api_version.endswith("3"):
            print(result)
            print(result["content"])
            data = result["content"][0]
            geom_wkt = data["geometry"]

        else:
            data = result["content"]
            geom_wkt = data["geometry"]

        for k in list(data.keys()):
            if k not in [u"geometry", u"centroid"]:
                attributes[k] = data[k]

        attributes["apikey"] = api_key
        attributes["host"] = base_url.lstrip('https://').rstrip(self.api_version)

        return attributes, geom_wkt

    def get_raster_list(self, base_url, api_key, parcel_id, product_id, data_source):
        """
         Gets the list of rasters from the given URL, API key, parcel id, product (e.g. vitality) and
         data source (e.g. sentinel2) from the agknow API.

        :param base_url: URL for the HTTP GET request
        :param api_key: API key for agknow
        :param parcel_id: parcel id
        :param product_id: choose a product (e.g. "vitality"|"visible"|"variations")
        :param data_source: set data source ( e.g. ""|"landsat8"|"sentinel2")

        :return: list of raster information dicts
        """
        params = "/parcels/{0}/{1}/?key={2}&source={3}".format(parcel_id, product_id, api_key, data_source)

        result = json.loads(self.sync_http_get(base_url, params))

        data = result["content"]

        return data

    def get_raster(self, base_url, api_key, parcel_id, product_id, data_source, raster_id, img_format="png"):
        """
         Gets a raster in the given file format from the API for the given URL, API key, parcel id,
         product (e.g. vitality) and data source (e.g. sentinel2) from the agknow API.

        :param base_url: URL for the HTTP GET request
        :param api_key: API key for agknow
        :param parcel_id: parcel id
        :param product_id: choose a product (e.g. "vitality"|"visible"|"variations")
        :param data_source: set data source (""|"landsat8"|"sentinel2")
        :param raster_id: raster_id of the image
        :param img_format: choose a image format ("png"|"tif")

        :return: the binary representation of the raster image
        """
        if product_id == "reflectances": # always tif
            params = "/parcels/{0}/{1}/{2}/{3}.{4}?key={5}".format(parcel_id, product_id, data_source, raster_id, "tif",
                                                                   api_key)
        else:
            params = "/parcels/{0}/{1}/{2}/{3}.{4}?key={5}".format(parcel_id, product_id, data_source, raster_id, img_format,
                                                                   api_key)

        result = self.sync_http_get(base_url, params, return_raw=True)

        return result

    def get_raster_bbox(self, base_url, api_key, parcel_id, product_id):
        """
        Get the bounding box of the image from the API for the given URL, API key, parcel id and product (e.g. vitality).
        Because all rasters of a parcel have the same bbox we simply take the bbox data from the first object.

        :param base_url: URL for the HTTP GET request
        :param api_key: API key for agknow
        :param parcel_id: parcel id
        :param product_id: choose a product (e.g. "vitality"|"visible"|"variations")

        :return: BoundingBox object as nested list (e.g. [[45.3434434, 10.64546464],[45.364434, 10.614546464]]
        """
        params = "/parcels/{0}/{1}/?key={2}".format(parcel_id, product_id, api_key)

        result = json.loads(self.sync_http_get(base_url, params))

        bbox = result["content"][0]["bounds"] # take the bbox from the first raster

        return bbox

    def get_gdal_metadata(self, gdal_dataset):
        """
         Gets GDAL metadata from the given GDAL dataset.
        :param gdal_dataset: GDAL dataset

        :return: A tuple of GDAL metadata with nodata_value, xsize, ysize, GDAL GeoTransform object, Projection, data type.
        """
        NDV = gdal_dataset.GetRasterBand(1).GetNoDataValue()
        xsize = gdal_dataset.RasterXSize
        ysize = gdal_dataset.RasterYSize
        GeoT = gdal_dataset.GetGeoTransform()
        Projection = osr.SpatialReference()
        Projection.ImportFromWkt(gdal_dataset.GetProjectionRef())
        DataType = gdal_dataset.GetRasterBand(1).DataType
        DataType = gdal.GetDataTypeName(DataType)

        return NDV, xsize, ysize, GeoT, Projection, DataType

    def georeference_raster(self, gdal_dataset, bbox, xsize, ysize, epsg_code=4326):
        """
         Georeference the given raster with the given data of bounding box, x and y size to the
         SRS of the given EPSG code.

        :param gdal_dataset: GDAL dataset
        :param bbox: Bounding Box in the format [[45.3434434, 10.64546464],[45.364434, 10.614546464]]
        :param xsize: X size of the dataset (width)
        :param ysize: Y size of the dataset (height)
        :param epsg_code: EPSG Code for the SRS to use in georeference operation.

        """
        ulx = minx = bbox[0][1]
        uly = miny = bbox[0][0]
        lrx = maxx = bbox[1][1]
        lry = maxy = bbox[1][0]
        image_width = xsize
        image_height = ysize

        # Specify raster location through geotransform array
        # (uperleftx, scalex, skewx, uperlefty, skewy, scaley)
        # Scale = size of one pixel in units of raster projection
        scalex = (maxx - minx) / image_width
        scaley = (maxy - miny) / image_height

        gt = [minx, scalex, 0, maxy, 0, scaley * -1]

        # Set bbox infos to original raster
        gdal_dataset.SetGeoTransform(gt)

        # Get raster projection
        epsg_dest = epsg_code
        srs_src = osr.SpatialReference()
        srs_dest = osr.SpatialReference()
        srs_src.ImportFromEPSG(epsg_code)
        srs_dest.ImportFromEPSG(epsg_dest)
        dest_wkt = srs_dest.ExportToWkt()

        # print GetGeoInfo(gdal_raster)
        # Set projection
        gdal_dataset.SetProjection(dest_wkt)

        # important! otherwise the projection is not set!
        gdal_dataset.FlushCache()

    def transform_raster(self, gdal_dataset, dst_epsg_code):
        """
         Transforms the given GDAL dataset in memory to the SRS of the given EPSG code.

        :param gdal_dataset: GDAL dataset
        :param dst_epsg_code: destination EPSG Code

        :return: The memory map string of the transformed GDAL dataset.
        """

        mmap_name = "/vsimem/{0}".format(uuid4().hex)

        gdal.Warp(mmap_name, gdal_dataset, dstSRS='EPSG:{0}'.format(dst_epsg_code))

        return mmap_name


    def download_image(self, api_key, base_url, parcel_id, product_id, raster_id, source, img_format, epsg):
        """
         Downloads, georeferences and transforms (if necessary) the raster image from the API with the given parameters.

        :param api_key:
        :param base_url:
        :param parcel_id:
        :param product_id:
        :param raster_id:
        :param source:
        :param img_format:
        :param epsg:

        :return: The memory map string of the transformed GDAL dataset.
        """
        img = self.get_raster(base_url, api_key, parcel_id, product_id, source, raster_id, img_format=img_format)

        mmap_name = "/vsimem/{0}".format(uuid4().hex)

        gdal.FileFromMemBuffer(mmap_name, img)
        dataset = gdal.Open(mmap_name)

        #print("original raster: {0}".format(mmap_name))

        NDV, xsize, ysize, GeoT, Projection, DataType = self.get_gdal_metadata(dataset)

        #print(NDV, xsize, ysize, GeoT, Projection, DataType)

        # PNG has to be referenced, Geotiff has the projection info already
        if img_format == 'png':

            bbox = self.get_raster_bbox(base_url, api_key, parcel_id, product_id)

            # original is WGS84 (because of bbox)
            self.georeference_raster(dataset, bbox, xsize, ysize, epsg_code=4326)

            #reproject raster
            # TODO only if EPSG codes differ!
            mmap_name = self.transform_raster(dataset, dst_epsg_code=epsg)
            #print("transformed raster: {0}".format(mmap_name))

        return mmap_name

    def exportGDALraster(self, mmap_name, out_path):
        """
         Exports a memory map GDAL raster to GeoTiff on disk.

        :param mmap_name:
        :param out_path:
        """

        in_dataset = gdal.Open(mmap_name)

        # Write output
        if out_path.upper().endswith(".TIF"):
            driver = gdal.GetDriverByName('Gtiff')
            # Output to new format
            out_dataset = driver.CreateCopy(out_path, in_dataset, strict=0,
                           options=["TILED=YES", "COMPRESS=DEFLATE"])

        elif out_path.upper().endswith(".PNG"):
            driver = gdal.GetDriverByName('PNG')
            # Output to new format
            out_dataset = driver.CreateCopy(out_path, in_dataset, strict=0,
                                            options=[])

        # Properly close the datasets to flush to disk
        out_dataset = None
        in_dataset = None
