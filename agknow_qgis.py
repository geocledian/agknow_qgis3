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
from builtins import object
from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, Qt, pyqtSlot # QGIS3!
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
# Initialize Qt resources from file resources.py
from . import resources

# Import the code for the DockWidget
from .agknow_qgis_dockwidget import AgknowDockWidget
from .agknow_qgis_dockwidget_timeslider import AgknowDockWidgetTimeSlider

from .agknow_worker import *

from qgis.core import QgsProject

import os.path

class Agknow(object):
    """Central plugin agknow class for QGIS which controls AgknowDockWidget and AgknowDockWidgetTimeSlider classes.
       Communication between the two Dockwiget instances has been implemented with pyqtSignals and pyqtSlots."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgisInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'Agknow_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&agknow for QGIS')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'Agknow')
        self.toolbar.setObjectName(u'Agknow')

        #print "** INITIALIZING Agknow"

        self.pluginIsActive = False
        self.main_dockwidget = None
        self.timeslider_dockwidget = None

        self.data_source = "all"
        self.product = "vitality"


    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('Agknow', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip="",
        whats_this="",
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action


    def initGui(self):
        """
        Create the menu entries and toolbar icons inside the QGIS GUI.
        """

        icon_path = ':/plugins/Agknow/agknow_project_logo.png'
        self.add_action(
            icon_path,
            text=self.tr(u'agknow for QGIS'),
            status_tip="agknow for QGIS",
            callback=self.run,
            parent=self.iface.mainWindow())

    #--------------------------------------------------------------------------

    def onClosePlugin(self):
        """
        Cleanup necessary items here when any plugin dockwidget is closed
        """

        print("** CLOSING Agknow")

        print("saving settings..")
        self.save_settings()

        self.clear_plugin_layers()

        # custom events
        self.main_dockwidget.imagesReloaded.disconnect(self.onImagesReloaded)
        self.main_dockwidget.dataSourceChanged.disconnect(self.onDatasourceChanged)
        self.main_dockwidget.parcelIdChanged.disconnect(self.onParcelIdChanged)
        self.timeslider_dockwidget.productChanged.disconnect(self.onProductChanged)

        # closing events
        self.main_dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.timeslider_dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS to crash
        # when closing the docked window:
        # remove also all other dockwidgets from the GUI
        self.iface.removeDockWidget(self.main_dockwidget)
        self.iface.removeDockWidget(self.timeslider_dockwidget)

        self.main_dockwidget = None
        self.timeslider_dockwidget = None

        self.pluginIsActive = False


    def unload(self):
        """
        Removes the plugin menu item and icon from QGIS GUI.
        """

        print("** UNLOAD Agknow")

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&agknow for QGIS'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

        self.clear_plugin_layers()

    def clear_plugin_layers(self):
        """
        Clears parcel & img layer of agknow_qgis
        """
        try:
            root = QgsProject.instance().layerTreeRoot()

            # clear images
            img_group = root.findGroup("images")

            if img_group is not None:
                root.findGroup("images").removeAllChildren()
                root.removeChildNode(img_group)

            # clear parcel layer
            #parcelLyr = self.main_dockwidget.get_parcel_lyr()
            #if parcelLyr is not None:
            #    QgsProject.instance().removeMapLayer(parcelLyr)

            # alternate
            for l in root.findLayers():
                # QGIS >= 2.18.1 : name(), QGIS 2.18.0 : layerName()
                if l.name() == u"parcels":
                    root.removeLayer(l.layer())

        except Exception as e:
            print(str(e))

    #--------------------------------------------------------------------------

    def run(self):
        """
        Run method that loads and starts the plugin
        """

        if not self.pluginIsActive:
            self.pluginIsActive = True

            #print "** STARTING Agknow"

            # dockwidget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.main_dockwidget == None:
                # Create the dockwidget (after translation) and keep reference
                self.main_dockwidget = AgknowDockWidget()

                # read agknow_qgis settings from QSettings
                self.read_settings()

            if self.timeslider_dockwidget == None:
                 # Create the dockwidget (after translation) and keep reference
                self.timeslider_dockwidget = AgknowDockWidgetTimeSlider()

            # connect to provide cleanup on closing of dockwidget
            self.main_dockwidget.closingPlugin.connect(self.onClosePlugin)
            self.timeslider_dockwidget.closingPlugin.connect(self.onClosePlugin)

            # custom events
            self.main_dockwidget.imagesReloaded.connect(self.onImagesReloaded)
            self.main_dockwidget.dataSourceChanged.connect(self.onDatasourceChanged)
            self.main_dockwidget.parcelIdChanged.connect(self.onParcelIdChanged)
            self.timeslider_dockwidget.productChanged.connect(self.onProductChanged)

            # show the dockwidgets
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.main_dockwidget)
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, self.timeslider_dockwidget)

            self.main_dockwidget.show()
            self.timeslider_dockwidget.show()


    #@pyqtSlot(str) - no decorator for QGIS3?
    def onDatasourceChanged(self, value):
        """
         Handles the event of onDatasourceChanged.

        :param value: data_source string "landsat8" or "sentinel2"
        """
        self.data_source = value
        # route change to timeslider dockwigdet
        self.timeslider_dockwidget.set_data_source(value)

    #@pyqtSlot(str) - no decorator for QGIS3?
    def onProductChanged(self, value):
        """
         Handles the event of onProductChanged.

        :param value: product string (e.g. "vitality", "variations", "ndvi", "ndre1" ...)

        """
        self.product = value
        # route change to main dockwigdet
        self.main_dockwidget.set_product(value)

    #@pyqtSlot() - no decorator for QGIS3?
    def onImagesReloaded(self, rasters):
        """
         Handles the event of onImagesReloaded for the given rasters.
         :param rasters:
        """
        print("onImagesReloaded()")
        self.timeslider_dockwidget.reload_images(rasters)

    #@pyqtSlot(int) - no decorator for QGIS3?
    def onParcelIdChanged(self, parcel_id):
        """
         Handles the event of onParcelIdChanged for the given parcel_id.
        :param parcel_id:
        """
        self.timeslider_dockwidget.set_current_parcel_id(parcel_id)

    # settings
    def save_settings(self):
        """
         Saves Agknow plugin settings to the global QSettings object
        """
        s = QSettings()
        s.setValue("agknow_qgis/host_url", self.main_dockwidget.tbHostURL.text())
        s.setValue("agknow_qgis/api_key", self.main_dockwidget.tbAPIKey.text())

    def read_settings(self):
        """
         Reads Agknow plugin settings from global QSettings object
        """
        s = QSettings()
        # read from key or take the default values
        base_url = s.value("agknow_qgis/host_url", "https://geocledian.com")
        api_key = s.value("agknow_qgis/api_key", "39553fb7-7f6f-4945-9b84-a4c8745bdbec")

        self.main_dockwidget.tbHostURL.setText(base_url)
        self.main_dockwidget.tbAPIKey.setText(api_key)
