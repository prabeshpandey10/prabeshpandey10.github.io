"""
Fire Hazard Heatmap Toolbox
===========================
ArcGIS Pro Python Toolbox (.pyt)

Author : Prabesh Pandey
         M.S. Applied Geography — Texas State University
         Co-authors: Mussie Wolday Tsegay & Md Saroar Hossain

Description:
    Generates a kernel-density fire-hazard heatmap from a CSV of
    groundwater/temperature point data, clips it to a user-supplied
    study boundary, and loads the result into the active ArcGIS Pro map.

Requirements:
    - ArcGIS Pro 3.x
    - Spatial Analyst extension

Input CSV must contain:
    latitude        : decimal degrees (WGS 84)
    longitude       : decimal degrees (WGS 84)
    water_depth_ft  : numeric field used as the population/weight field
                      (or any other numeric field the user selects)
"""

import arcpy
import os


class Toolbox(object):
    def __init__(self):
        self.label   = "Fire Hazard Heatmap Toolbox"
        self.alias   = "firehazard"
        self.tools   = [GenerateHeatmap]


class GenerateHeatmap(object):

    def __init__(self):
        self.label       = "Generate Fire Hazard Heatmap"
        self.description = (
            "Creates a kernel-density heatmap from a CSV of groundwater / "
            "temperature point data and clips it to a study boundary shapefile."
        )
        self.canRunInBackground = False

    # ------------------------------------------------------------------
    def getParameterInfo(self):
        params = []

        # 0 — Input CSV
        in_csv = arcpy.Parameter(
            displayName   = "Input Fire Hazard CSV",
            name          = "in_csv",
            datatype      = "DETable",
            parameterType = "Required",
            direction     = "Input")
        params.append(in_csv)

        # 1 — Latitude field (defaults to 'latitude')
        lat_field = arcpy.Parameter(
            displayName   = "Latitude Field",
            name          = "lat_field",
            datatype      = "Field",
            parameterType = "Required",
            direction     = "Input")
        lat_field.parameterDependencies = ["in_csv"]
        lat_field.value = "latitude"
        params.append(lat_field)

        # 2 — Longitude field (defaults to 'longitude')
        lon_field = arcpy.Parameter(
            displayName   = "Longitude Field",
            name          = "lon_field",
            datatype      = "Field",
            parameterType = "Required",
            direction     = "Input")
        lon_field.parameterDependencies = ["in_csv"]
        lon_field.value = "longitude"
        params.append(lon_field)

        # 3 — Heat / weight field
        heat_field = arcpy.Parameter(
            displayName   = "Heat Field (e.g. water_depth_ft or avg_temp)",
            name          = "heat_field",
            datatype      = "Field",
            parameterType = "Required",
            direction     = "Input")
        heat_field.parameterDependencies = ["in_csv"]
        params.append(heat_field)

        # 4 — Study boundary (shapefile or feature class)
        boundary = arcpy.Parameter(
            displayName   = "Study Boundary (shapefile or feature class)",
            name          = "boundary",
            datatype      = "DEFeatureClass",
            parameterType = "Required",
            direction     = "Input")
        params.append(boundary)

        # 5 — Cell size (decimal degrees)
        cell_size = arcpy.Parameter(
            displayName   = "Cell Size (decimal degrees)",
            name          = "cell_size",
            datatype      = "GPDouble",
            parameterType = "Optional",
            direction     = "Input")
        cell_size.value = 0.01
        params.append(cell_size)

        # 6 — Output raster
        out_raster = arcpy.Parameter(
            displayName   = "Output Heatmap Raster",
            name          = "out_raster",
            datatype      = "DERasterDataset",
            parameterType = "Required",
            direction     = "Output")
        params.append(out_raster)

        return params

    # ------------------------------------------------------------------
    def isLicensed(self):
        """Require Spatial Analyst for KernelDensity and ExtractByMask."""
        try:
            return arcpy.CheckExtension("Spatial") == "Available"
        except Exception:
            return False

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        if not self.isLicensed():
            parameters[0].setErrorMessage(
                "Spatial Analyst extension is required but not available."
            )

    # ------------------------------------------------------------------
    def execute(self, parameters, messages):
        arcpy.CheckOutExtension("Spatial")

        in_csv     = parameters[0].valueAsText
        lat_field  = parameters[1].valueAsText
        lon_field  = parameters[2].valueAsText
        heat_field = parameters[3].valueAsText
        boundary   = parameters[4].valueAsText
        cell_size  = float(parameters[5].value) if parameters[5].value else 0.01
        out_raster = parameters[6].valueAsText

        temp_ws   = arcpy.env.scratchGDB
        points_fc = os.path.join(temp_ws, "firehazard_points")

        # ── Step 1: CSV → point feature class ──────────────────────────
        messages.addMessage("Step 1/4 — Converting CSV to point features...")
        if arcpy.Exists(points_fc):
            arcpy.management.Delete(points_fc)

        arcpy.management.XYTableToPoint(
            in_table             = in_csv,
            out_feature_class    = points_fc,
            x_field              = lon_field,
            y_field              = lat_field,
            coordinate_system    = arcpy.SpatialReference(4326)   # WGS 84
        )
        count = int(arcpy.management.GetCount(points_fc)[0])
        messages.addMessage(f"  {count:,} points created.")

        # ── Step 2: Kernel Density ──────────────────────────────────────
        messages.addMessage("Step 2/4 — Running Kernel Density (this may take a moment)...")
        kernel = arcpy.sa.KernelDensity(
            in_point_or_polyline_features = points_fc,
            population_field              = heat_field,
            cell_size                     = cell_size
        )
        temp_kernel = os.path.join(temp_ws, "temp_kernel_raster")
        kernel.save(temp_kernel)
        messages.addMessage("  Kernel density raster created.")

        # ── Step 3: Clip to boundary ────────────────────────────────────
        messages.addMessage("Step 3/4 — Clipping raster to study boundary...")
        clipped = arcpy.sa.ExtractByMask(temp_kernel, boundary)
        clipped.save(out_raster)
        messages.addMessage(f"  Clipped heatmap saved to: {out_raster}")

        # ── Step 4: Add to map ──────────────────────────────────────────
        messages.addMessage("Step 4/4 — Adding output to active map...")
        try:
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            m    = aprx.activeMap
            if m:
                m.addDataFromPath(out_raster)
                messages.addMessage("  Heatmap layer added to active map.")
            else:
                messages.addMessage("  No active map found — open a map and add the raster manually.")
        except Exception as e:
            messages.addMessage(f"  Could not add to map automatically: {e}")

        arcpy.CheckInExtension("Spatial")
        messages.addMessage("Done. Fire hazard heatmap complete.")
