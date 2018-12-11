# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Agknow
                                 A QGIS plugin
 Plugin for using the agknow API from geo|cledian
                             -------------------
        begin                : 2018-07-18
        copyright            : (C) 2018 by geo|cledian.com
        email                : jsommer@geocledian.com
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load Agknow class from file Agknow.

    :param iface: A QGIS interface instance.
    :type iface: QgisInterface
    """
    #
    from .agknow_qgis import Agknow
    return Agknow(iface)
