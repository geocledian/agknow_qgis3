PLUGINNAME="agknow_qgis"
VERSION="0.7.3-beta"
QGISDIR=$HOME"/.local/share/QGIS/QGIS3/profiles/default/python/plugins"
BUILDDIR="./build/"$PLUGINNAME
ZIPDIR="./build"
ZIPFILE=$BUILDDIR"3_"$VERSION".zip"

unzip -o $ZIPFILE -d $QGISDIR
