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

#配置
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
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"map_source": "OpenStreetMap (WGS84)", "output_dir": os.getcwd()}


def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)


pi = 3.1415926535897932384626
x_pi = 3.14159265358979324 * 3000.0 / 180.0
a = 6378245.0
ee = 0.00669342162296594323


def out_of_china(lng, lat):
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def transform_lat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 * math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * pi) + 40.0 * math.sin(lat / 3.0 * pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * pi) + 320 * math.sin(lat * pi / 30.0)) * 2.0 / 3.0
    return ret


def transform_lng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 * math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * pi) + 40.0 * math.sin(lng / 3.0 * pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * pi) + 300.0 * math.sin(lng / 30.0 * pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lng, lat):
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
    if out_of_china(lng, lat): return lng, lat
    dlng, dlat = wgs84_to_gcj02(lng, lat)
    return lng * 2 - dlng, lat * 2 - dlat


def gcj02_to_bd09(lng, lat):
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * x_pi)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * x_pi)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def bd09_to_gcj02(lng, lat):
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
    return z * math.cos(theta), z * math.sin(theta)


def wgs84_to_bd09(lng, lat):
    lng, lat = wgs84_to_gcj02(lng, lat)
    return gcj02_to_bd09(lng, lat)


def bd09_to_wgs84(lng, lat):
    lng, lat = bd09_to_gcj02(lng, lat)
    return gcj02_to_wgs84(lng, lat)


# UI
class CoordConverterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("坐标系转换工具")
        self.setMinimumWidth(350)
        layout = QFormLayout(self)

        self.in_lon = QLineEdit()
        self.in_lat = QLineEdit()
        layout.addRow("经度 (Lng):", self.in_lon)
        layout.addRow("纬度 (Lat):", self.in_lat)

        self.cs_from = QComboBox()
        self.cs_from.addItems(["WGS84", "GCJ02 (高德/腾讯)", "BD09 (百度)"])
        self.cs_to = QComboBox()
        self.cs_to.addItems(["WGS84", "GCJ02 (高德/腾讯)", "BD09 (百度)"])

        layout.addRow("源坐标系:", self.cs_from)
        layout.addRow("目标坐标系:", self.cs_to)

        btn_convert = QPushButton("转换")
        btn_convert.clicked.connect(self.do_convert)
        layout.addRow(btn_convert)

        self.out_lon = QLineEdit()
        self.out_lat = QLineEdit()
        self.out_lon.setReadOnly(True)
        self.out_lat.setReadOnly(True)
        layout.addRow("结果经度:", self.out_lon)
        layout.addRow("结果纬度:", self.out_lat)

    def do_convert(self):
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
            QMessageBox.warning(self, "错误", "请输入有效的数字！")


# 设置对话框
class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings_data=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(400)
        self.settings_data = settings_data

        layout = QFormLayout(self)
        self.map_combo = QComboBox()
        self.map_combo.addItems(list(MAP_SOURCES.keys()))
        self.map_combo.setCurrentText(self.settings_data.get("map_source", "OpenStreetMap (WGS84)"))
        layout.addRow("底图源:", self.map_combo)

        out_layout = QHBoxLayout()
        self.out_path_edit = QLineEdit(self.settings_data.get("output_dir", os.getcwd()))
        btn_browse = QPushButton("浏览")
        btn_browse.clicked.connect(self.browse_dir)
        out_layout.addWidget(self.out_path_edit)
        out_layout.addWidget(btn_browse)
        layout.addRow("默认输出目录:", out_layout)

        btn_save = QPushButton("保存配置")
        btn_save.clicked.connect(self.save_settings)
        layout.addRow(btn_save)

    def browse_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "输出目录")
        if directory: self.out_path_edit.setText(directory)

    def save_settings(self):
        self.settings_data["map_source"] = self.map_combo.currentText()
        self.settings_data["output_dir"] = self.out_path_edit.text()
        save_settings(self.settings_data)
        self.accept()


# 切割
class CropThread(QThread):
    status_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, input_pbf, output_pbf, bbox):
        super().__init__()
        self.input_pbf = input_pbf
        self.output_pbf = output_pbf
        self.bbox = bbox

    def run(self):
        cmd = ["osmconvert.exe", self.input_pbf, f"-b={self.bbox}", "--complete-ways", f"-o={self.output_pbf}"]
        try:
            self.status_signal.emit(f"执行命令: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.finished_signal.emit(True, f"切割完成！保存至: {self.output_pbf}")
        except subprocess.CalledProcessError as e:
            self.finished_signal.emit(False, f"切割失败: {e.stderr}")
        except Exception as e:
            self.finished_signal.emit(False, f"异常: {str(e)}")


# 主窗口
class OSMTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OSM切割工具 v0.1")
        self.resize(1100, 750)
        self.sys_config = load_settings()

        self.setAcceptDrops(True)

        self.init_menu()
        self.init_ui()
        self.init_map()

    # 拖拽事件处理
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith('.pbf'):
                self.input_path.setText(file_path)
            else:
                self.log_output.append("⚠️ 提示：请拖入 .osm.pbf 格式的文件。")

    def init_menu(self):
        menubar = self.menuBar()
        etc_menu = menubar.addMenu("其他(&O)")

        act_settings = etc_menu.addAction("系统设置")
        act_convert = etc_menu.addAction("坐标系转换工具")

        act_settings.triggered.connect(self.open_settings)
        act_convert.triggered.connect(self.open_converter)

    def open_converter(self):
        CoordConverterDialog(self).exec()

    def init_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        # 左侧面板
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        file_layout = QHBoxLayout()
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("可将 .pbf 文件拖拽到此处导入")
        btn_browse = QPushButton("浏览")
        btn_browse.clicked.connect(self.browse_file)
        file_layout.addWidget(self.input_path)
        file_layout.addWidget(btn_browse)
        left_layout.addWidget(QLabel("源文件:"))
        left_layout.addLayout(file_layout)

        left_layout.addWidget(QLabel("裁剪边界坐标(WGS84标准): \n提示: 在右侧地图【右键】可直接点选，且自动防呆纠正大小"))
        self.min_lon = QLineEdit()
        self.min_lon.setPlaceholderText("起点 经度 Min Lng (左下)")
        self.min_lat = QLineEdit()
        self.min_lat.setPlaceholderText("起点 纬度 Min Lat (左下)")
        self.max_lon = QLineEdit()
        self.max_lon.setPlaceholderText("终点 经度 Max Lng (右上)")
        self.max_lat = QLineEdit()
        self.max_lat.setPlaceholderText("终点 纬度 Max Lat (右上)")

        for w in [self.min_lon, self.min_lat, self.max_lon, self.max_lat]:
            left_layout.addWidget(w)
            w.editingFinished.connect(self.check_and_draw_bbox)

        #清除
        btn_clear = QPushButton("清除坐标与选区")
        btn_clear.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 5px;")
        btn_clear.clicked.connect(self.clear_coords)
        left_layout.addWidget(btn_clear)

        self.btn_run = QPushButton("切割并导出")
        self.btn_run.setFixedHeight(40)
        self.btn_run.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold;")
        self.btn_run.clicked.connect(self.start_crop)
        left_layout.addWidget(self.btn_run)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        left_layout.addWidget(self.log_output)

        splitter.addWidget(left_widget)

        #右面板
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.map_view = QWebEngineView()
        right_layout.addWidget(self.map_view)

        splitter.addWidget(right_widget)
        splitter.setSizes([350, 750])

    def clear_coords(self):
        self.min_lon.clear()
        self.min_lat.clear()
        self.max_lon.clear()
        self.max_lat.clear()
        js_code = "if(currentRect) { map.removeLayer(currentRect); currentRect = null; }"
        self.map_view.page().runJavaScript(js_code)
        self.log_output.append("已清空当前坐标与地图选区。")

    def init_map(self):
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

                // 地图源显示
                var infoControl = L.control({{position: 'bottomright'}});
                infoControl.onAdd = function (map) {{
                    var div = L.DomUtil.create('div');
                    div.innerHTML = `<div style="background: rgba(255,255,255,0.85); padding: 4px 8px; font-size: 11px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); pointer-events: none;">
                        <b>{source_key}</b>
                    </div>`;
                    return div;
                }};
                infoControl.addTo(map);

                // 矩形选框
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
                                <div style="text-align: center; font-weight: bold; font-size: 14px; margin-bottom:8px;">自动纠偏取点</div>

                                <div style="background: #fff3e0; border-left: 4px solid #ff9800; padding: 6px; margin-bottom: 6px;">
                                    <div style="color: #e65100; font-size: 12px; margin-bottom:2px;">当前坐标系:GCJ02</div>
                                    <div style="font-family: monospace;">${{rawLng.toFixed(6)}},<br>${{rawLat.toFixed(6)}}</div>
                                </div>

                                <div style="background: #e8f5e9; border-left: 4px solid #4caf50; padding: 6px; margin-bottom: 12px;">
                                    <div style="color: #2e7d32; font-size: 12px; font-weight: bold; margin-bottom:2px;">OSRM坐标系:WGS84</div>
                                    <div style="font-family: monospace; font-weight: bold;">${{finalLng.toFixed(6)}},<br>${{finalLat.toFixed(6)}}</div>
                                </div>
                        `;
                    }} else {{
                        contentHtml = `
                            <div style="font-size: 13px; min-width: 180px;">
                                <div style="text-align: center; font-weight: bold; font-size: 14px; margin-bottom:8px;">坐标取点</div>
                                <div style="background: #e8f5e9; border-left: 4px solid #4caf50; padding: 6px; margin-bottom: 12px;">
                                    <div style="color: #2e7d32; font-size: 12px; font-weight: bold; margin-bottom:2px;">OSRM坐标系:WGS84</div>
                                    <div style="font-family: monospace; font-weight: bold;">${{finalLng.toFixed(6)}},<br>${{finalLat.toFixed(6)}}</div>
                                </div>
                        `;
                    }}

                    contentHtml += `
                                <button onclick="document.title='FILL:MIN:${{finalLng}}:${{finalLat}}';" style="width:100%; padding:8px; background:#4CAF50; color:white; border:none; border-radius:4px; cursor:pointer; margin-bottom:6px; font-weight:bold;">切割起点</button><br>
                                <button onclick="document.title='FILL:MAX:${{finalLng}}:${{finalLat}}';" style="width:100%; padding:8px; background:#2196F3; color:white; border:none; border-radius:4px; cursor:pointer; font-weight:bold;">切割终点</button>
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
                self.log_output.append("已自动重排对角线坐标")

            js_code = f"if(typeof drawBBox === 'function') drawBBox({min_lon}, {min_lat}, {max_lon}, {max_lat});"
            self.map_view.page().runJavaScript(js_code)

        except ValueError:
            pass

    def on_map_title_changed(self, title):
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
        dialog = SettingsDialog(self, self.sys_config)
        if dialog.exec():
            self.init_map()

    def browse_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "选择 PBF 文件", "", "OSM Files (*.pbf)")
        if filename: self.input_path.setText(filename)

    def start_crop(self):
        input_pbf = self.input_path.text()
        if not os.path.exists(input_pbf):
            self.log_output.append("错误：输入文件不存在！")
            return

        self.check_and_draw_bbox()

        bbox = f"{self.min_lon.text()},{self.min_lat.text()},{self.max_lon.text()},{self.max_lat.text()}"
        out_dir = self.sys_config.get("output_dir", os.getcwd())
        output_pbf = os.path.join(out_dir, f"output_{self.min_lon.text()}_{self.min_lat.text()}.osm.pbf")

        self.btn_run.setEnabled(False)
        self.log_output.append(f"正在启动切割任务... 导出至 {output_pbf}")

        self.thread = CropThread(input_pbf, output_pbf, bbox)
        self.thread.status_signal.connect(lambda msg: self.log_output.append(msg))
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, success, message):
        self.btn_run.setEnabled(True)
        self.log_output.append(message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OSMTool()
    window.show()
    window.log_output.append("请确保切割矩形起点坐标为左下角坐标,终点坐标为右上角坐标")
    sys.exit(app.exec())