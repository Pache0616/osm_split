# OSM PBF Cropping Tool v0.1

This is a PySide6-based graphical user interface (GUI) tool designed to help developers quickly crop OpenStreetMap `.pbf` data files via an interactive map . The tool features a built-in coordinate correction mechanism, making it highly suitable for extracting accurate regional road network data for the OSRM (Open Source Routing Machine) engine .

## Disclaimer
本工具仅供学习与技术研究使用。在处理、切割或转换测绘数据时，请务必遵守所在国家和地区的相关测绘法律法规!

## Features

* **Interactive Map Selection**: Integrates a Leaflet web map, allowing users to quickly set the crop rectangle's starting point (bottom-left) and ending point (top-right) using the right-click menu .
* **Multiple Map Sources**: Supports three base map sources: OpenStreetMap (WGS84), Gaode Map (GCJ02), and Esri Satellite (WGS84) .
* **Automatic Coordinate Correction**: When selecting points on a GCJ02 base map (e.g., Gaode), the system automatically converts the GCJ02 coordinates to the standard WGS84 coordinates required by OSRM .
* **Fail-Safe Coordinate Sorting**: Automatically compares the longitude and latitude of the start and end points . Regardless of the selection order, it rearranges them into a valid bottom-left/top-right diagonal bounding box .
* **Quick Import**: Supports drag-and-drop functionality to instantly load `.osm.pbf` data files into the main window .
* **Built-in Coordinate Converter**: Provides a standalone dialog tool for mutual conversions between WGS84, GCJ02, and BD09 coordinate systems .
* **Asynchronous Processing**: Cropping tasks run in an independent background thread using `QThread`, executing external command-line tools and printing logs in real-time without freezing the main UI .

## Requirements

* Python 3.x
* Core dependency: `PySide6` 
* External command-line tool: `osmconvert.exe` (Must be added to system environment variables or placed in the same directory as the program) 

## Configuration `setting.json`

The program automatically reads the `setting.json` file in the current directory upon startup . Supported configuration parameters include:
* `map_source`: The default base map loaded at startup .
* `output_dir`: The default output directory for cropped files .
* `enable_gpu`: Flag to enable GPU hardware acceleration .
* `enable_sandbox`: Flag to enable sandbox security mode .

## Usage Guide

1. **Import File**: Click the "Browse" button or drag a `.pbf` file directly into the "Source File" input field .
2. **Select Area**: Locate the target area on the right-side map, right-click, and select "Crop Start Point" and "Crop End Point" .
3. **Execute Crop**: Verify the coordinate parameters on the left panel and click the "Crop and Export" button .
4. **View Results**: Cropping logs will be output in real-time in the bottom-left text box. The finished file will be saved to your configured output directory .