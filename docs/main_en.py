import sys
import os
import json
import math
import subprocess

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QFileDialog, QTextEdit, QProgressBar, QSplitter,
                               QMenuBar, QMenu, QDialog, QComboBox, QFormLayout, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView

# Configuration
SETTINGS_FILE = "setting.json"

MAP_SOURCES = {
    "OpenStreetMap (WGS84)": {
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "crs": "WGS84"
    },
    "高德地图 (GCJ02)": {
        "url": "https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        "crs": "GCJ02"
    },
    "Esri 卫星图 (WGS84)": {
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "crs": "WGS84"
    }
}


def load_settings():
    """
    Loads the application settings[cite: 1].
    Attempts to read the local setting.json file. If the file does not exist or fails to load,
    it returns a default configuration (OpenStreetMap and current working directory)[cite: 1].

    :return: A dictionary containing the configuration data[cite: 1].
    """
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"map_source": "OpenStreetMap (WGS84)", "output_dir": os.getcwd()}


def save_settings(settings):
    """
    Saves the configuration data to the setting.json file[cite: 1].
    Uses UTF-8 encoding and formats the JSON output with a 4-space indent[cite: 1].

    :param settings: A dictionary containing the settings to be saved[cite: 1].
    """
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)


# Constants for coordinate system mathematical conversion formulas[cite: 1]
pi = 3.1415926535897932384626
x_pi = 3.14159265358979324 * 3000.0 / 180.0
a = 6378245.0
ee = 0.00669342162296594323


def out_of_china(lng, lat):
    """
    Determines whether the given coordinates are outside of China[cite: 1].
    If outside China, GCJ02 offset correction is not required[cite: 1].

    :param lng: Longitude[cite: 1]
    :param lat: Latitude[cite: 1]
    :return: Boolean value; returns True if outside China, False otherwise[cite: 1].
    """
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def transform_lat(lng, lat):
    """
    Calculates the offset for latitude[cite: 1].
    """
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 * math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * pi) + 40.0 * math.sin(lat / 3.0 * pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * pi) + 320 * math.sin(lat * pi / 30.0)) * 2.0 / 3.0
    return ret


def transform_lng(lng, lat):
    """
    Calculates the offset for longitude[cite: 1].
    """
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 * math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * pi) + 40.0 * math.sin(lng / 3.0 * pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * pi) + 300.0 * math.sin(lng / 30.0 * pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lng, lat):
    """
    Converts WGS84 standard coordinates to GCJ02 (used by Gaode/Tencent)[cite: 1].
    """
    if out_of_china(lng, lat): return lng, lat
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * pi)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng, lat):
    """
    Converts GCJ02 coordinates to standard WGS84 coordinates[cite: 1].
    """
    if out_of_china(lng, lat): return lng, lat
    dlng, dlat = wgs84_to_gcj02(lng, lat)
    return lng * 2 - dlng, lat * 2 - dlat


def gcj02_to_bd09(lng, lat):
    """
    Converts GCJ02 coordinates to BD09 (Baidu coordinate system)[cite: 1].
    """
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * x_pi)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * x_pi)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def bd09_to_gcj02(lng, lat):
    """
    Converts BD09 coordinates to GCJ02 coordinates[cite: 1].
    """
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
    return z * math.cos(theta), z * math.sin(theta)


def wgs84_to_bd09(lng, lat):
    """
    Converts WGS84 standard coordinates to BD09 coordinates[cite: 1].
    """
    lng, lat = wgs84_to_gcj02(lng, lat)
    return gcj02_to_bd09(lng, lat)


def bd09_to_wgs84(lng, lat):
    """
    Converts BD09 coordinates to standard WGS84 coordinates[cite: 1].
    """
    lng, lat = bd09_to_gcj02(lng, lat)
    return gcj02_to_wgs84(lng, lat)


# UI Components
class CoordConverterDialog(QDialog):
    """
    Standalone coordinate conversion dialog UI class[cite: 1].
    Provides functionality for users to manually input and convert between WGS84, GCJ02, and BD09[cite: 1].
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Coordinate Converter Tool")
        self.setMinimumWidth(350)
        layout = QFormLayout(self)

        self.in_lon = QLineEdit()
        self.in_lat = QLineEdit()
        layout.addRow("Longitude (Lng):", self.in_lon)
        layout.addRow("Latitude (Lat):", self.in_lat)

        self.cs_from = QComboBox()
        self.cs_from.addItems(["WGS84", "GCJ02 (Gaode/Tencent)", "BD09 (Baidu)"])
        self.cs_to = QComboBox()
        self.cs_to.addItems(["WGS84", "GCJ02 (Gaode/Tencent)", "BD09 (Baidu)"])

        layout.addRow("Source CRS:", self.cs_from)
        layout.addRow("Target CRS:", self.cs_to)

        btn_convert = QPushButton("Convert")
        btn_convert.clicked.connect(self.do_convert)
        layout.addRow(btn_convert)

        self.out_lon = QLineEdit()
        self.out_lat = QLineEdit()
        self.out_lon.setReadOnly(True)
        self.out_lat.setReadOnly(True)
        layout.addRow("Result Lng:", self.out_lon)
        layout.addRow("Result Lat:", self.out_lat)

    def do_convert(self):
        """
        Callback function to handle core conversion logic[cite: 1].
        Identifies the source and target coordinate systems from the comboboxes and applies the corresponding conversion formula[cite: 1].
        """
        try:
            lng, lat = float(self.in_lon.text()), float(self.in_lat.text())
            c_from, c_to = self.cs_from.currentText()[:5], self.cs_to.currentText()[:5]
            if c_from == "GCJ02":
                lng, lat = gcj02_to_wgs84(lng, lat)
            elif c_from == "BD09 ":
                lng, lat = bd09_to_wgs84(lng, lat)
            if c_to == "GCJ02":
                lng, lat = wgs84_to_gcj02(lng, lat)
            elif c_to == "BD09 ":
                lng, lat = wgs84_to_bd09(lng, lat)
            self.out_lon.setText(f"{lng:.6f}")
            self.out_lat.setText(f"{lat:.6f}")
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter valid numeric values!")


# Settings Dialog
class SettingsDialog(QDialog):
    """
    System settings dialog UI class[cite: 1].
    Allows users to select the base map source, configure the default output directory, and persist settings to a json file[cite: 1].
    """

    def __init__(self, parent=None, settings_data=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        self.settings_data = settings_data

        layout = QFormLayout(self)
        self.map_combo = QComboBox()
        self.map_combo.addItems(list(MAP_SOURCES.keys()))
        self.map_combo.setCurrentText(self.settings_data.get("map_source", "OpenStreetMap (WGS84)"))
        layout.addRow("Base Map Source:", self.map_combo)

        out_layout = QHBoxLayout()
        self.out_path_edit = QLineEdit(self.settings_data.get("output_dir", os.getcwd()))
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_dir)
        out_layout.addWidget(self.out_path_edit)
        out_layout.addWidget(btn_browse)
        layout.addRow("Default Output Dir:", out_layout)

        btn_save = QPushButton("Save Settings")
        btn_save.clicked.connect(self.save_settings)
        layout.addRow(btn_save)

    def browse_dir(self):
        """Opens a file explorer dialog to select and update the output directory path[cite: 1]."""
        directory = QFileDialog.getExistingDirectory(self, "Output Directory")
        if directory: self.out_path_edit.setText(directory)

    def save_settings(self):
        """Saves user-modified settings from the UI and closes the dialog[cite: 1]."""
        self.settings_data["map_source"] = self.map_combo.currentText()
        self.settings_data["output_dir"] = self.out_path_edit.text()
        save_settings(self.settings_data)
        self.accept()


# Cropping Thread
class CropThread(QThread):
    """
    Asynchronous background cropping task class based on QThread[cite: 1].
    Used to invoke the external osmconvert.exe tool to execute underlying PBF cropping,
    preventing command-line blocking from freezing the graphical interface[cite: 1].
    """
    status_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, input_pbf, output_pbf, bbox):
        """
        Initializes thread parameters[cite: 1].
        :param input_pbf: Source PBF file path[cite: 1]
        :param output_pbf: Target exported PBF file path[cite: 1]
        :param bbox: Cropping boundary box, format: 'min_lon,min_lat,max_lon,max_lat'[cite: 1]
        """
        super().__init__()
        self.input_pbf = input_pbf
        self.output_pbf = output_pbf
        self.bbox = bbox

    def run(self):
        """
        Executes external command-line instructions for data cropping[cite: 1].
        Runs via subprocess and emits status feedback to the main thread via Signal[cite: 1].
        """
        cmd = ["osmconvert.exe", self.input_pbf, f"-b={self.bbox}", "--complete-ways", f"-o={self.output_pbf}"]
        try:
            self.status_signal.emit(f"Executing command: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.finished_signal.emit(True, f"Cropping complete! Saved to: {self.output_pbf}")
        except subprocess.CalledProcessError as e:
            self.finished_signal.emit(False, f"Cropping failed: {e.stderr}")
        except Exception as e:
            self.finished_signal.emit(False, f"Exception: {str(e)}")


# Main Window
class OSMTool(QMainWindow):
    """
    Main application window class[cite: 1].
    Integrates file drag-and-drop parsing, parameter input, map web container, and execution log display modules[cite: 1].
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OSM Cropping Tool v0.1")
        self.resize(1100, 750)
        self.sys_config = load_settings()

        self.setAcceptDrops(True)

        self.init_menu()
        self.init_ui()
        self.init_map()

    def dragEnterEvent(self, event):
        """Identifies dragged objects entering the window; allows drop if it contains URLs (files)[cite: 1]."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handles drop events, extracts the pbf file path, and auto-fills the input field. Prints a warning if format is incorrect[cite: 1]."""
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith('.pbf'):
                self.input_path.setText(file_path)
            else:
                self.log_output.append("⚠️ Notice: Please drop a file with the .osm.pbf extension.")

    def init_menu(self):
        """Initializes the top menu bar, including entries for system settings and the coordinate conversion tool[cite: 1]."""
        menubar = self.menuBar()
        etc_menu = menubar.addMenu("Other(&O)")

        act_settings = etc_menu.addAction("System Settings")
        act_convert = etc_menu.addAction("Coordinate Converter")

        act_settings.triggered.connect(self.open_settings)
        act_convert.triggered.connect(self.open_converter)

    def open_converter(self):
        """Opens the standalone coordinate converter dialog[cite: 1]."""
        CoordConverterDialog(self).exec()

    def init_ui(self):
        """
        Initializes the split-screen layout for the main interface[cite: 1].
        Left panel for operational controls (I/O, coordinate boxes, logs); Right panel for the WebEngine map view[cite: 1].
        """
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        # Left Panel
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        file_layout = QHBoxLayout()
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("Drag and drop .pbf file here")
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_file)
        file_layout.addWidget(self.input_path)
        file_layout.addWidget(btn_browse)
        left_layout.addWidget(QLabel("Source File:"))
        left_layout.addLayout(file_layout)

        left_layout.addWidget(QLabel(
            "Crop Bounding Box (WGS84 Standard): \nTip: [Right-click] on the map to select points. Auto fail-safe size correction is enabled."))
        self.min_lon = QLineEdit()
        self.min_lon.setPlaceholderText("Start Min Lng (Bottom-Left)")
        self.min_lat = QLineEdit()
        self.min_lat.setPlaceholderText("Start Min Lat (Bottom-Left)")
        self.max_lon = QLineEdit()
        self.max_lon.setPlaceholderText("End Max Lng (Top-Right)")
        self.max_lat = QLineEdit()
        self.max_lat.setPlaceholderText("End Max Lat (Top-Right)")

        for w in [self.min_lon, self.min_lat, self.max_lon, self.max_lat]:
            left_layout.addWidget(w)
            w.editingFinished.connect(self.check_and_draw_bbox)

        # Clear button
        btn_clear = QPushButton("Clear Coordinates & Selection")
        btn_clear.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 5px;")
        btn_clear.clicked.connect(self.clear_coords)
        left_layout.addWidget(btn_clear)

        self.btn_run = QPushButton("Crop and Export")
        self.btn_run.setFixedHeight(40)
        self.btn_run.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold;")
        self.btn_run.clicked.connect(self.start_crop)
        left_layout.addWidget(self.btn_run)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        left_layout.addWidget(self.log_output)

        splitter.addWidget(left_widget)

        # Right Panel
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.map_view = QWebEngineView()
        right_layout.addWidget(self.map_view)

        splitter.addWidget(right_widget)
        splitter.setSizes([350, 750])

    def clear_coords(self):
        """Clears coordinate input fields on the left UI and removes the red bounding rectangle from the map via JS injection[cite: 1]."""
        self.min_lon.clear()
        self.min_lat.clear()
        self.max_lon.clear()
        self.max_lat.clear()
        js_code = "if(currentRect) { map.removeLayer(currentRect); currentRect = null; }"
        self.map_view.page().runJavaScript(js_code)
        self.log_output.append("Current coordinates and map selection cleared.")

    def init_map(self):
        """
        Initializes HTML and JS code for the web map and injects it into QWebEngineView[cite: 1].
        Internally loads map tiles via Leaflet and implements web-side coordinate conversion (handles GCJ02 offset to match OSRM required WGS84)[cite: 1].
        """
        source_key = self.sys_config.get("map_source", "OpenStreetMap (WGS84)")
        map_info = MAP_SOURCES.get(source_key, MAP_SOURCES["OpenStreetMap (WGS84)"])
        tile_url = map_info["url"]

        is_gcj02_js = "true" if map_info["crs"] == "GCJ02" else "false"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css"/>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
            <style>body, html, #map {{width: 100%; height: 100%; margin: 0; padding: 0;}}</style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                var PI = 3.1415926535897932384626;
                var a = 6378245.0;
                var ee = 0.00669342162296594323;

                function outOfChina(lng, lat) {{ return !(lng > 73.66 && lng < 135.05 && lat > 3.86 && lat < 53.55); }}
                function transformLat(lng, lat) {{
                    var ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * Math.sqrt(Math.abs(lng));
                    ret += (20.0 * Math.sin(6.0 * lng * PI) + 20.0 * Math.sin(2.0 * lng * PI)) * 2.0 / 3.0;
                    ret += (20.0 * Math.sin(lat * PI) + 40.0 * Math.sin(lat / 3.0 * PI)) * 2.0 / 3.0;
                    ret += (160.0 * Math.sin(lat / 12.0 * PI) + 320 * Math.sin(lat * PI / 30.0)) * 2.0 / 3.0;
                    return ret;
                }}
                function transformLng(lng, lat) {{
                    var ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * Math.sqrt(Math.abs(lng));
                    ret += (20.0 * Math.sin(6.0 * lng * PI) + 20.0 * Math.sin(2.0 * lng * PI)) * 2.0 / 3.0;
                    ret += (20.0 * Math.sin(lng * PI) + 40.0 * Math.sin(lng / 3.0 * PI)) * 2.0 / 3.0;
                    ret += (150.0 * Math.sin(lng / 12.0 * PI) + 300.0 * Math.sin(lng / 30.0 * PI)) * 2.0 / 3.0;
                    return ret;
                }}
                function wgs84ToGcj02(lng, lat) {{
                    if (outOfChina(lng, lat)) return [lng, lat];
                    var dlat = transformLat(lng - 105.0, lat - 35.0);
                    var dlng = transformLng(lng - 105.0, lat - 35.0);
                    var radlat = lat / 180.0 * PI;
                    var magic = Math.sin(radlat);
                    magic = 1 - ee * magic * magic;
                    var sqrtmagic = Math.sqrt(magic);
                    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * PI);
                    dlng = (dlng * 180.0) / (a / sqrtmagic * Math.cos(radlat) * PI);
                    return [lng + dlng, lat + dlat];
                }}
                function gcj02ToWgs84(lng, lat) {{
                    if (outOfChina(lng, lat)) return [lng, lat];
                    var gcj = wgs84ToGcj02(lng, lat);
                    return [lng * 2 - gcj[0], lat * 2 - gcj[1]];
                }}

                var map = L.map('map').setView([35.8617, 104.1954], 4);
                L.tileLayer('{tile_url}', {{ maxZoom: 18 }}).addTo(map);
                var popup = L.popup();
                var isGcj02 = {is_gcj02_js};

                // Show map source
                var infoControl = L.control({{position: 'bottomright'}});
                infoControl.onAdd = function (map) {{
                    var div = L.DomUtil.create('div');
                    div.innerHTML = `<div style="background: rgba(255,255,255,0.85); padding: 4px 8px; font-size: 11px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); pointer-events: none;">
                        <b>{source_key}</b>
                    </div>`;
                    return div;
                }};
                infoControl.addTo(map);

                // Drawing bounding box
                var currentRect = null;
                function drawBBox(minLng, minLat, maxLng, maxLat) {{
                    if (currentRect) {{ map.removeLayer(currentRect); }}
                    var bounds = [[minLat, minLng], [maxLat, maxLng]];
                    currentRect = L.rectangle(bounds, {{color: "#ff0000", weight: 2, fillOpacity: 0.15}}).addTo(map);
                    map.flyToBounds(bounds, {{padding: [30, 30], duration: 0.5}});
                }}

                map.on('contextmenu', function(e) {{
                    var rawLat = e.latlng.lat;
                    var rawLng = e.latlng.lng;
                    var finalLat = rawLat, finalLng = rawLng;
                    var contentHtml = '';

                    if (isGcj02) {{
                        var wgs = gcj02ToWgs84(rawLng, rawLat);
                        finalLng = wgs[0]; finalLat = wgs[1];
                        contentHtml = `
                            <div style="font-size: 13px; min-width: 200px;">
                                <div style="text-align: center; font-weight: bold; font-size: 14px; margin-bottom:8px;">Auto Offset Point Selection</div>

                                <div style="background: #fff3e0; border-left: 4px solid #ff9800; padding: 6px; margin-bottom: 6px;">
                                    <div style="color: #e65100; font-size: 12px; margin-bottom:2px;">Current CRS: GCJ02</div>
                                    <div style="font-family: monospace;">${{rawLng.toFixed(6)}},<br>${{rawLat.toFixed(6)}}</div>
                                </div>

                                <div style="background: #e8f5e9; border-left: 4px solid #4caf50; padding: 6px; margin-bottom: 12px;">
                                    <div style="color: #2e7d32; font-size: 12px; font-weight: bold; margin-bottom:2px;">OSRM CRS: WGS84</div>
                                    <div style="font-family: monospace; font-weight: bold;">${{finalLng.toFixed(6)}},<br>${{finalLat.toFixed(6)}}</div>
                                </div>
                        `;
                    }} else {{
                        contentHtml = `
                            <div style="font-size: 13px; min-width: 180px;">
                                <div style="text-align: center; font-weight: bold; font-size: 14px; margin-bottom:8px;">Point Selection</div>
                                <div style="background: #e8f5e9; border-left: 4px solid #4caf50; padding: 6px; margin-bottom: 12px;">
                                    <div style="color: #2e7d32; font-size: 12px; font-weight: bold; margin-bottom:2px;">OSRM CRS: WGS84</div>
                                    <div style="font-family: monospace; font-weight: bold;">${{finalLng.toFixed(6)}},<br>${{finalLat.toFixed(6)}}</div>
                                </div>
                        `;
                    }}

                    contentHtml += `
                                <button onclick="document.title='FILL:MIN:${{finalLng}}:${{finalLat}}';" style="width:100%; padding:8px; background:#4CAF50; color:white; border:none; border-radius:4px; cursor:pointer; margin-bottom:6px; font-weight:bold;">Crop Start Point</button><br>
                                <button onclick="document.title='FILL:MAX:${{finalLng}}:${{finalLat}}';" style="width:100%; padding:8px; background:#2196F3; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:bold;">Crop End Point</button>
                            </div>
                    `;
                    popup.setLatLng(e.latlng).setContent(contentHtml).openOn(map);
                }});

                map.on('click', function(e) {{
                    document.title = "COORD:" + e.latlng.lng.toFixed(6) + "," + e.latlng.lat.toFixed(6);
                }});
            </script>
        </body>
        </html>
        """
        self.map_view.setHtml(html_content)
        self.map_view.titleChanged.connect(self.on_map_title_changed)

    def check_and_draw_bbox(self):
        """
        Reads and validates the four inputted coordinate values, executing an auto fail-safe sorting[cite: 1].
        Ensures the start point is always the bottom-left (min_lon, min_lat) and the end point is the top-right (max_lon, max_lat); then triggers JS to draw the rectangle[cite: 1].
        """
        try:
            lon1, lat1 = float(self.min_lon.text()), float(self.min_lat.text())
            lon2, lat2 = float(self.max_lon.text()), float(self.max_lat.text())

            min_lon, max_lon = min(lon1, lon2), max(lon1, lon2)
            min_lat, max_lat = min(lat1, lat2), max(lat1, lat2)

            if lon1 != min_lon or lat1 != min_lat or lon2 != max_lon or lat2 != max_lat:
                self.min_lon.setText(f"{min_lon:.6f}")
                self.min_lat.setText(f"{min_lat:.6f}")
                self.max_lon.setText(f"{max_lon:.6f}")
                self.max_lat.setText(f"{max_lat:.6f}")
                self.log_output.append("Automatically rearranged diagonal coordinates.")

            js_code = f"if(typeof drawBBox === 'function') drawBBox({min_lon}, {min_lat}, {max_lon}, {max_lat});"
            self.map_view.page().runJavaScript(js_code)

        except ValueError:
            pass

    def on_map_title_changed(self, title):
        """
        Receives and parses commands sent from the web map back to Python (achieved by modifying document.title)[cite: 1].
        If it's an assignment command for the start/end point (FILL:MIN / FILL:MAX), it populates the left text fields and updates the drawing[cite: 1].

        :param title: The title string sent from the web end[cite: 1]
        """
        if title.startswith("FILL:"):
            parts = title.split(":")
            target = parts[1]
            lng, lat = float(parts[2]), float(parts[3])

            if target == "MIN":
                self.min_lon.setText(f"{lng:.6f}")
                self.min_lat.setText(f"{lat:.6f}")
            else:
                self.max_lon.setText(f"{lng:.6f}")
                self.max_lat.setText(f"{lat:.6f}")

            self.check_and_draw_bbox()

    def open_settings(self):
        """Opens the settings dialog, and upon confirming save, refreshes the map engine (if the base map was changed)[cite: 1]."""
        dialog = SettingsDialog(self, self.sys_config)
        if dialog.exec():
            self.init_map()

    def browse_file(self):
        """Opens a file dialog allowing users to manually select a .pbf file to be cropped[cite: 1]."""
        filename, _ = QFileDialog.getOpenFileName(self, "Select PBF File", "", "OSM Files (*.pbf)")
        if filename: self.input_path.setText(filename)

    def start_crop(self):
        """
        Preparation and parameter validation prior to executing the cropping task[cite: 1].
        Assembles output paths, disables execution buttons, and starts the asynchronous CropThread to prevent UI freezing[cite: 1].
        """
        input_pbf = self.input_path.text()
        if not os.path.exists(input_pbf):
            self.log_output.append("Error: Input file does not exist!")
            return

        self.check_and_draw_bbox()

        bbox = f"{self.min_lon.text()},{self.min_lat.text()},{self.max_lon.text()},{self.max_lat.text()}"
        out_dir = self.sys_config.get("output_dir", os.getcwd())
        output_pbf = os.path.join(out_dir, f"output_{self.min_lon.text()}_{self.min_lat.text()}.osm.pbf")

        self.btn_run.setEnabled(False)
        self.log_output.append(f"Starting crop task... Exporting to {output_pbf}")

        self.thread = CropThread(input_pbf, output_pbf, bbox)
        self.thread.status_signal.connect(lambda msg: self.log_output.append(msg))
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, success, message):
        """
        Handles callbacks for when the cropping task completes or exits with exceptions[cite: 1].
        Restores the "Crop and Export" button status and prints the final log messages[cite: 1].

        :param success: Boolean indicating if the task ran successfully[cite: 1]
        :param message: Return message or error log passed back by the thread[cite: 1]
        """
        self.btn_run.setEnabled(True)
        self.log_output.append(message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OSMTool()
    window.show()
    window.log_output.append(
        "Please ensure the crop rectangle start point is the bottom-left coordinate, and the end point is the top-right coordinate.")
    sys.exit(app.exec())