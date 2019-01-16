# agknow for QGIS 3.x
This plugin allows the usage of the remote sensing API ag|knowledge from geo|cledian.com. 
The API provides a field monitoring service that allows to monitor any agricultural field worldwide 
with a variety of vegetation indexes, crop parameters, times series analysis and comparison features based on satellite data.
<p>
Features of the plugin include the download and analysis of time series of visible and vegetation indexes rasters of registered fields. The data is based on Landsat-8 and Sentinel-2 currently. 
See <a href="https://sites.google.com/site/geocledian">https://sites.google.com/site/geocledian</a> for a detailed product overwiew.
<p>
Please note that you will need a registered API key from geocledian.com to use this plugin for your area of interest. The plugin is delivered with a demo key that allows to access some demo parcels around the world for evaluation purposes.

## Why?
- Convenient tool for Analysts if they want to work with the data of the agknow API directly in a desktop GIS
  especially for GeoTiff reflectances and indices
- Export parcel data
- Viewer for GeoTiff output of the API; the Javascript clients will not work here 

## Features:
- Version 0.7.2:
  - Parcel registering for selected feature from QGIS layer
- Version 0.7.1:
  - Download of all parcels for specified key -> QGIS feature layer
  - Download of all images (PNG or GeoTiff) -> QGIS raster layer
  - Grouping of layers according to their data sources/products/time stamps
  - Timeseries of images with timeslider widget
  - respects current SRS of project for downloading images/parcels from agknow API
  - anything happens in memory (vector and image data)

## Installation
### Linux
clone git repo to ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins
### Windows
clone git repo to %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins, i.e.
C:\Users\[USER]\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins


