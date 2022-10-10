PLUGINNAME="agknow_qgis"
BUILDDIR="./build/"$PLUGINNAME
ZIPDIR="./build"

mkdir -p $BUILDDIR

cp *.py $BUILDDIR
cp *.ui $BUILDDIR
cp metadata.txt $BUILDDIR
cp README.md $BUILDDIR
cp LICENSE $BUILDDIR
cp agknow_project_logo.png $BUILDDIR
cp agknow_project_logo.jpg $BUILDDIR
cp parcels-style-yellow.qml $BUILDDIR
cp resources.qrc $BUILDDIR
cp *.png $BUILDDIR


