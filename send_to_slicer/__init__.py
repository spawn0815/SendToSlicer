# SPDX-License-Identifier: GPL-3.0-or-later
# Send to Slicer - export selected Blender objects straight into your slicer.
# Copyright (C) 2026 Dennis Fuchs

import glob
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zipfile

import bmesh
import bpy
import numpy as np
from mathutils.bvhtree import BVHTree
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       PointerProperty, StringProperty)

ADDON_ID = __package__ or __name__

EXPORTABLE_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}

# Self-intersection test is skipped above this many triangles (too slow)
SELF_INTERSECT_MAX_TRIS = 400_000


# ---------------------------------------------------------------------------
# Slicer detection
# ---------------------------------------------------------------------------

# key: (display name, Windows paths, macOS app bundles, Linux commands / AppImages)
# Paths may contain environment variables and glob wildcards.
KNOWN_SLICERS = {
    "ANYCUBIC": (
        "Anycubic Slicer Next",
        [r"%ProgramFiles%\AnycubicSlicerNext\AnycubicSlicerNext.exe",
         r"%ProgramFiles%\Anycubic Slicer Next\AnycubicSlicerNext.exe",
         r"%LOCALAPPDATA%\Programs\AnycubicSlicerNext\AnycubicSlicerNext.exe"],
        ["/Applications/AnycubicSlicerNext.app", "/Applications/Anycubic Slicer Next.app"],
        ["AnycubicSlicerNext", "~/Applications/AnycubicSlicerNext*.AppImage"],
    ),
    "ORCA": (
        "OrcaSlicer",
        [r"%ProgramFiles%\OrcaSlicer\orca-slicer.exe",
         r"%LOCALAPPDATA%\Programs\OrcaSlicer\orca-slicer.exe"],
        ["/Applications/OrcaSlicer.app"],
        ["orca-slicer", "~/Applications/OrcaSlicer*.AppImage"],
    ),
    "BAMBU": (
        "Bambu Studio",
        [r"%ProgramFiles%\Bambu Studio\bambu-studio.exe"],
        ["/Applications/BambuStudio.app", "/Applications/Bambu Studio.app"],
        ["bambu-studio", "~/Applications/Bambu_Studio*.AppImage"],
    ),
    "PRUSA": (
        "PrusaSlicer",
        [r"%ProgramFiles%\Prusa3D\PrusaSlicer\prusa-slicer.exe"],
        ["/Applications/PrusaSlicer.app", "/Applications/Original Prusa Drivers/PrusaSlicer.app"],
        ["prusa-slicer", "~/Applications/PrusaSlicer*.AppImage"],
    ),
    "CURA": (
        "UltiMaker Cura",
        [r"%ProgramFiles%\UltiMaker Cura*\UltiMaker-Cura.exe"],
        ["/Applications/UltiMaker Cura*.app"],
        ["cura", "~/Applications/UltiMaker-Cura*.AppImage"],
    ),
}

SLICER_ITEMS = [("AUTO", "Auto-detect", "Use the first installed slicer from the list")]
SLICER_ITEMS += [(key, data[0], f"Send to {data[0]}") for key, data in KNOWN_SLICERS.items()]
SLICER_ITEMS += [("CUSTOM", "Custom program", "Any slicer that opens files passed on the command line")]

_detect_cache = {}
_DETECT_CACHE_SECONDS = 10.0


def _locate(key):
    _name, win, mac, linux = KNOWN_SLICERS[key]
    if sys.platform == "win32":
        for pattern in win:
            matches = sorted(glob.glob(os.path.expandvars(pattern)), reverse=True)  # newest version first
            if matches:
                return matches[0]
    elif sys.platform == "darwin":
        for pattern in mac:
            matches = sorted(glob.glob(pattern), reverse=True)
            if matches:
                return matches[0]
    else:
        for entry in linux:
            if "/" in entry:
                matches = sorted(glob.glob(os.path.expanduser(entry)), reverse=True)
                if matches:
                    return matches[0]
            elif shutil.which(entry):
                return shutil.which(entry)
    return None


def find_slicer(context):
    """Returns (display name, path) of the configured slicer, or (display name, None) if not found."""
    prefs = get_prefs(context)
    choice = prefs.slicer if prefs else "AUTO"
    if choice == "CUSTOM":
        path = bpy.path.abspath(prefs.custom_path) if prefs.custom_path else ""
        name = os.path.splitext(os.path.basename(path.rstrip("/\\")))[0] or "Custom program"
        return name, (path if path and os.path.exists(path) else None)

    cached = _detect_cache.get(choice)
    if cached and time.monotonic() - cached[0] < _DETECT_CACHE_SECONDS:
        return cached[1]

    keys = list(KNOWN_SLICERS) if choice == "AUTO" else [choice]
    found = ("Slicer" if choice == "AUTO" else KNOWN_SLICERS[choice][0], None)
    for key in keys:
        path = _locate(key)
        if path:
            found = (KNOWN_SLICERS[key][0], path)
            break
    _detect_cache[choice] = (time.monotonic(), found)
    return found


def _clear_detect_cache(_self=None, _context=None):
    _detect_cache.clear()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_prefs(context):
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def default_export_dir():
    return os.path.join(tempfile.gettempdir(), "blender_send_to_slicer")


class STS_Preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    slicer: EnumProperty(
        name="Slicer",
        description="Which slicer to open the exported files in",
        items=SLICER_ITEMS,
        default="AUTO",
        update=_clear_detect_cache,
    )
    custom_path: StringProperty(
        name="Program",
        description="Path to the slicer executable (on macOS: the .app bundle)",
        subtype="FILE_PATH",
        update=_clear_detect_cache,
    )
    export_dir: StringProperty(
        name="Export Folder",
        description="Folder for the temporary export files. Empty = system temp folder",
        subtype="DIR_PATH",
    )

    def draw(self, context):
        draw_slicer_settings(self.layout, context, self)


def draw_slicer_settings(layout, context, prefs):
    col = layout.column()
    col.prop(prefs, "slicer")
    if prefs.slicer == "CUSTOM":
        col.prop(prefs, "custom_path")
    name, path = find_slicer(context)
    if path:
        col.label(text=f"Found: {path}", icon="CHECKMARK")
    else:
        col.label(text=f"{name} not found - choose another slicer or a custom program", icon="ERROR")
    col.prop(prefs, "export_dir")
    if not prefs.export_dir:
        col.label(text=f"Default: {default_export_dir()}", icon="INFO")


class STS_CheckResult(bpy.types.PropertyGroup):
    # name = object name
    level: EnumProperty(items=[("OK", "OK", ""), ("WARN", "Warning", ""), ("ERROR", "Error", "")])
    text: StringProperty()  # lines separated by "\n"


class STS_Settings(bpy.types.PropertyGroup):
    file_format: EnumProperty(
        name="Format",
        items=[("3MF", "3MF", "Keeps object names and units, several objects in one file"),
               ("STL", "STL", "Universal, but without units and names")],
        default="3MF",
    )
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Export the result of all modifiers. The objects in Blender are not changed",
        default=True,
    )
    file_mode: EnumProperty(
        name="Files",
        items=[("SINGLE", "One File", "All selected objects in one file"),
               ("SEPARATE", "Separate", "One file per object")],
        default="SINGLE",
    )
    place_on_bed: BoolProperty(
        name="Place on Bed",
        description="Move the selection as a whole to Z = 0 and to the center of the build plate. "
                    "Distances between the objects are kept",
        default=True,
    )
    unit_mode: EnumProperty(
        name="Units",
        items=[("SCENE", "From Scene", "Convert to mm using the scene's unit settings"),
               ("MANUAL", "Manual", "Own factor: 1 Blender unit = x mm")],
        default="SCENE",
    )
    manual_factor: FloatProperty(
        name="1 BU = mm",
        description="How many millimeters one Blender unit should be",
        default=1.0, min=1e-6, soft_max=1000.0,
    )
    check_before_send: BoolProperty(
        name="Check Before Sending",
        description="Run the print check before every send and warn about problems (sending is not blocked)",
        default=True,
    )
    check_self_intersections: BoolProperty(
        name="Self-Intersections",
        description="Look for faces that cut through each other. Can take a moment on very dense meshes",
        default=True,
    )
    bed_x: FloatProperty(name="X", default=250.0, min=1.0)
    bed_y: FloatProperty(name="Y", default=250.0, min=1.0)
    bed_z: FloatProperty(name="Z", default=250.0, min=1.0)
    min_size: FloatProperty(
        name="Minimum Size (mm)",
        description="Objects whose largest side is smaller are reported as probably wrongly scaled",
        default=2.0, min=0.0,
    )

    results: CollectionProperty(type=STS_CheckResult)
    results_info: StringProperty()
    show_results: BoolProperty(name="Results", default=True)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def mm_factor(scene, settings):
    if settings.unit_mode == "MANUAL":
        return settings.manual_factor
    us = scene.unit_settings
    if us.system == "NONE":
        return 1.0  # no unit system: 1 BU = 1 mm (common convention for 3D printing)
    # scale_length: 1 BU = scale_length meters
    return us.scale_length * 1000.0


def export_objects(context):
    return [o for o in context.selected_objects if o.type in EXPORTABLE_TYPES]


def object_triangles(obj, depsgraph, apply_modifiers, factor):
    """Returns (verts[N,3] in mm, world space; tris[M,3]) of an object."""
    if apply_modifiers:
        src = obj.evaluated_get(depsgraph)
        mesh = src.to_mesh()
    else:
        src = obj
        mesh = obj.to_mesh()
    try:
        mesh.calc_loop_triangles()
        nv = len(mesh.vertices)
        nt = len(mesh.loop_triangles)
        verts = np.empty(nv * 3, dtype=np.float64)
        mesh.vertices.foreach_get("co", verts)
        tris = np.empty(nt * 3, dtype=np.int64)
        mesh.loop_triangles.foreach_get("vertices", tris)
    finally:
        src.to_mesh_clear()

    verts = verts.reshape(-1, 3)
    tris = tris.reshape(-1, 3)
    mat = np.array(obj.matrix_world, dtype=np.float64)
    verts = (verts @ mat[:3, :3].T + mat[:3, 3]) * factor
    if np.linalg.det(mat[:3, :3]) < 0:
        # negative scale mirrors the mesh -> flip winding, otherwise the normals point inwards
        tris = tris[:, ::-1]
    return verts, tris


def signed_volume(verts, tris):
    v0, v1, v2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def analyse_object(obj, depsgraph, settings, factor):
    """Checks one object and returns (level, [messages])."""
    verts, tris = object_triangles(obj, depsgraph, settings.apply_modifiers, factor)
    msgs, level = [], "OK"

    def warn(text):
        nonlocal level
        msgs.append("⚠ " + text)
        if level == "OK":
            level = "WARN"

    def error(text):
        nonlocal level
        msgs.append("✖ " + text)
        level = "ERROR"

    if len(tris) == 0:
        error("No faces - nothing to print")
        return level, msgs

    size = verts.max(axis=0) - verts.min(axis=0)
    msgs.append(f"Size: {size[0]:.2f} × {size[1]:.2f} × {size[2]:.2f} mm")

    # --- topology via bmesh (same geometry as the export) ---
    bm = bmesh.new()
    try:
        bm_verts = [bm.verts.new(co) for co in verts]
        bm.verts.ensure_lookup_table()
        dup_faces = 0
        for a, b, c in tris:
            try:
                bm.faces.new((bm_verts[a], bm_verts[b], bm_verts[c]))
            except ValueError:
                dup_faces += 1  # duplicate or degenerate face
        bm.edges.ensure_lookup_table()

        boundary = sum(1 for e in bm.edges if e.is_boundary)
        multi = sum(1 for e in bm.edges if len(e.link_faces) > 2)
        flipped = sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous)
        wire = sum(1 for e in bm.edges if e.is_wire)
        loose_verts = sum(1 for v in bm.verts if not v.link_edges)
        degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-10)

        closed = boundary == 0 and multi == 0
        if boundary:
            error(f"Not watertight: {boundary} open edges (holes)")
        if multi:
            error(f"{multi} edges shared by more than 2 faces (non-manifold)")
        if flipped:
            warn(f"{flipped} edges with inconsistent normals")
        if wire or loose_verts:
            warn(f"Loose geometry: {wire} edges, {loose_verts} vertices without faces")
        if degenerate or dup_faces:
            warn(f"{degenerate + dup_faces} degenerate/duplicate triangles")

        if settings.check_self_intersections:
            if len(tris) <= SELF_INTERSECT_MAX_TRIS:
                tree = BVHTree.FromBMesh(bm, epsilon=1e-5)
                overlap = tree.overlap(tree)
                if overlap:
                    faces = {i for pair in overlap for i in pair}
                    warn(f"{len(faces)} faces intersect each other")
            else:
                msgs.append(f"Self-intersection check skipped (> {SELF_INTERSECT_MAX_TRIS:,} triangles)")
    finally:
        bm.free()

    # --- volume / normal direction (only meaningful for a closed, consistently oriented mesh) ---
    if closed and not flipped:
        vol = signed_volume(verts, tris)
        if vol < 0:
            error("Normals point inwards (mesh is inside out)")
        msgs.append(f"Volume: {abs(vol) / 1000.0:.2f} cm³")

    # --- size / units ---
    biggest = float(size.max())
    if biggest < settings.min_size:
        error(f"Very small ({biggest:.3f} mm) - wrong units? (meters instead of mm?)")
    bed = (settings.bed_x, settings.bed_y, settings.bed_z)
    footprint_fits = (size[0] <= bed[0] and size[1] <= bed[1]) or (size[0] <= bed[1] and size[1] <= bed[0])
    if not footprint_fits or size[2] > bed[2]:
        if biggest > 10 * max(bed):
            error(f"Huge ({biggest:.0f} mm) - wrong units? (mm instead of meters?)")
        else:
            warn(f"Does not fit on the build plate ({bed[0]:.0f} × {bed[1]:.0f} × {bed[2]:.0f} mm)")

    if obj.type == "MESH" and obj.modifiers and not settings.apply_modifiers:
        msgs.append("Note: modifiers are not applied")

    if level == "OK":
        msgs.insert(0, "✔ Ready to print")
    return level, msgs


def run_check(context):
    scene = context.scene
    settings = scene.send_to_slicer
    depsgraph = context.evaluated_depsgraph_get()
    factor = mm_factor(scene, settings)
    settings.results.clear()
    worst = "OK"
    rank = {"OK": 0, "WARN": 1, "ERROR": 2}
    for obj in export_objects(context):
        level, msgs = analyse_object(obj, depsgraph, settings, factor)
        item = settings.results.add()
        item.name = obj.name
        item.level = level
        item.text = "\n".join(msgs)
        if rank[level] > rank[worst]:
            worst = level
    settings.results_info = f"1 Blender unit = {factor:g} mm"
    settings.show_results = True
    return worst


# ---------------------------------------------------------------------------
# File export
# ---------------------------------------------------------------------------

def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "object"


def write_stl(path, parts):
    """Binary STL; all parts are merged into one mesh."""
    tri_coords = np.concatenate([v[t] for _, v, t in parts]).astype(np.float32)  # (M,3,3)
    normals = np.cross(tri_coords[:, 1] - tri_coords[:, 0], tri_coords[:, 2] - tri_coords[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, lengths, out=np.zeros_like(normals), where=lengths > 0)
    data = np.zeros(len(tri_coords), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    data["n"] = normals
    data["v"] = tri_coords
    with open(path, "wb") as f:
        f.write(b"Exported from Blender by Send to Slicer".ljust(80, b" "))
        f.write(struct.pack("<I", len(data)))
        f.write(data.tobytes())


def _xml_escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;"))


def write_3mf(path, parts):
    """3MF core specification, unit millimeter, one <object> per Blender object."""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        '</Relationships>'
    )
    chunks = ['<?xml version="1.0" encoding="UTF-8"?>\n'
              '<model unit="millimeter" xml:lang="en-US" '
              'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
              '<metadata name="Application">Blender - Send to Slicer</metadata>'
              '<resources>']
    for i, (name, verts, tris) in enumerate(parts, start=1):
        chunks.append(f'<object id="{i}" name="{_xml_escape(name)}" type="model"><mesh><vertices>')
        chunks.append("".join(f'<vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in verts.tolist()))
        chunks.append("</vertices><triangles>")
        chunks.append("".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris.tolist()))
        chunks.append("</triangles></mesh></object>")
    chunks.append("</resources><build>")
    chunks.append("".join(f'<item objectid="{i}"/>' for i in range(1, len(parts) + 1)))
    chunks.append("</build></model>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("3D/3dmodel.model", "".join(chunks))


def prepare_export_dir(context):
    prefs = get_prefs(context)
    path = bpy.path.abspath(prefs.export_dir) if prefs and prefs.export_dir else default_export_dir()
    os.makedirs(path, exist_ok=True)
    # clean up old exports - only our own file types
    for entry in os.listdir(path):
        if entry.lower().endswith((".stl", ".3mf")):
            try:
                os.remove(os.path.join(path, entry))
            except OSError:
                pass  # file may still be open in the slicer
    return path


def export_files(context):
    scene = context.scene
    settings = scene.send_to_slicer
    depsgraph = context.evaluated_depsgraph_get()
    factor = mm_factor(scene, settings)

    parts = []
    for obj in export_objects(context):
        verts, tris = object_triangles(obj, depsgraph, settings.apply_modifiers, factor)
        if len(tris):
            parts.append((obj.name, verts, tris))
    if not parts:
        return []

    if settings.place_on_bed:
        lo = np.min([v.min(axis=0) for _, v, _ in parts], axis=0)
        hi = np.max([v.max(axis=0) for _, v, _ in parts], axis=0)
        offset = np.array([settings.bed_x / 2 - (lo[0] + hi[0]) / 2,
                           settings.bed_y / 2 - (lo[1] + hi[1]) / 2,
                           -lo[2]])
        parts = [(n, v + offset, t) for n, v, t in parts]

    out_dir = prepare_export_dir(context)
    ext = settings.file_format.lower()
    writer = write_3mf if settings.file_format == "3MF" else write_stl

    if settings.file_mode == "SINGLE":
        if len(parts) == 1:
            base = parts[0][0]
        else:
            base = bpy.path.display_name_from_filepath(bpy.data.filepath) or "blender_export"
        groups = [(safe_name(base), parts)]
    else:
        groups = [(safe_name(name), [(name, v, t)]) for name, v, t in parts]

    files, used = [], set()
    for base, group in groups:
        fname, n = base, 2
        while fname.lower() in used:
            fname, n = f"{base}_{n}", n + 1
        used.add(fname.lower())
        path = os.path.join(out_dir, f"{fname}.{ext}")
        writer(path, group)
        files.append(path)
    return files


def launch_slicer(exe, files):
    if sys.platform == "darwin" and exe.rstrip("/").endswith(".app"):
        subprocess.Popen(["open", "-a", exe, *files], close_fds=True)
        return
    kwargs = {"close_fds": True, "cwd": os.path.dirname(exe)}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([exe, *files], **kwargs)


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class STS_OT_send(bpy.types.Operator):
    bl_idname = "send_to_slicer.send"
    bl_label = "Send to Slicer"
    bl_description = "Export the selected objects and open them in the slicer"

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and bool(export_objects(context))

    def execute(self, context):
        name, exe = find_slicer(context)
        if not exe:
            self.report({"ERROR"}, f"{name} not found - check the slicer in the add-on preferences")
            return {"CANCELLED"}

        settings = context.scene.send_to_slicer
        worst = "OK"
        if settings.check_before_send:
            worst = run_check(context)

        try:
            files = export_files(context)
        except OSError as exc:
            self.report({"ERROR"}, f"Export failed: {exc}")
            return {"CANCELLED"}
        if not files:
            self.report({"ERROR"}, "The selected objects have no faces")
            return {"CANCELLED"}

        try:
            launch_slicer(exe, files)
        except OSError as exc:
            self.report({"ERROR"}, f"Could not start {name}: {exc}")
            return {"CANCELLED"}

        if worst == "ERROR":
            self.report({"WARNING"}, f"Sent to {name}, but the check found errors (see panel)")
        elif worst == "WARN":
            self.report({"WARNING"}, f"Sent to {name}, but the check found warnings (see panel)")
        else:
            self.report({"INFO"}, f"Sent {len(files)} file(s) to {name}")
        return {"FINISHED"}


class STS_OT_check(bpy.types.Operator):
    bl_idname = "send_to_slicer.check"
    bl_label = "Check"
    bl_description = "Check the selected objects for watertightness, normals, self-intersections and size"

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and bool(export_objects(context))

    def execute(self, context):
        worst = run_check(context)
        n = len(context.scene.send_to_slicer.results)
        msg = {"OK": f"{n} object(s) checked - all good",
               "WARN": f"{n} object(s) checked - warnings found",
               "ERROR": f"{n} object(s) checked - errors found"}[worst]
        self.report({"INFO"} if worst == "OK" else {"WARNING"}, msg)
        return {"FINISHED"}


class STS_OT_show_problems(bpy.types.Operator):
    bl_idname = "send_to_slicer.show_problems"
    bl_label = "Show Problems"
    bl_description = "Switch to Edit Mode and select open/non-manifold edges (does not change the mesh)"

    object_name: StringProperty()

    def execute(self, context):
        obj = context.scene.objects.get(self.object_name)
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Only possible for mesh objects")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for o in context.selected_objects:
            o.select_set(False)
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="EDGE")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.mesh.select_non_manifold()
        if obj.modifiers:
            self.report({"INFO"}, "Note: the selection shows the base mesh without modifiers")
        return {"FINISHED"}


class STS_OT_clear_results(bpy.types.Operator):
    bl_idname = "send_to_slicer.clear_results"
    bl_label = "Clear Results"

    def execute(self, context):
        context.scene.send_to_slicer.results.clear()
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------

class STS_PT_main(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Slicer"
    bl_label = "Send to Slicer"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.send_to_slicer
        objs = export_objects(context)
        name, exe = find_slicer(context)

        col = layout.column(align=True)
        col.label(text="Format:")
        col.row(align=True).prop(settings, "file_format", expand=True)
        col.separator()
        col.label(text="Multiple Objects:")
        col.row(align=True).prop(settings, "file_mode", expand=True)

        col = layout.column(align=True)
        col.prop(settings, "apply_modifiers")
        col.prop(settings, "place_on_bed")
        col.prop(settings, "check_before_send")

        layout.separator()
        row = layout.row()
        row.scale_y = 1.8
        label = f"Send to {name}" + (f" ({len(objs)})" if objs else "")
        row.operator(STS_OT_send.bl_idname, text=label, icon="EXPORT")
        if not objs:
            layout.label(text="No printable objects selected", icon="INFO")
        elif context.mode != "OBJECT":
            layout.label(text="Only available in Object Mode", icon="INFO")
        if not exe:
            layout.label(text=f"{name} not found (see Slicer below)", icon="ERROR")


class STS_PT_units(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Slicer"
    bl_label = "Units & Build Plate"
    bl_parent_id = "STS_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.send_to_slicer
        layout.row(align=True).prop(settings, "unit_mode", expand=True)
        if settings.unit_mode == "MANUAL":
            layout.prop(settings, "manual_factor")
        else:
            us = context.scene.unit_settings
            layout.label(text=f"Scene: {us.system.title()}, {us.length_unit.title()}")
        layout.label(text=f"1 Blender unit = {mm_factor(context.scene, settings):g} mm", icon="DRIVER_DISTANCE")

        layout.label(text="Build Plate (mm):")
        row = layout.row(align=True)
        row.prop(settings, "bed_x")
        row.prop(settings, "bed_y")
        row.prop(settings, "bed_z")
        layout.prop(settings, "min_size")


class STS_PT_check(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Slicer"
    bl_label = "Print Check"
    bl_parent_id = "STS_PT_main"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.send_to_slicer
        layout.prop(settings, "check_self_intersections")
        row = layout.row()
        row.scale_y = 1.3
        row.operator(STS_OT_check.bl_idname, icon="VIEWZOOM")

        if not settings.results:
            return
        header = layout.row()
        header.prop(settings, "show_results",
                    icon="TRIA_DOWN" if settings.show_results else "TRIA_RIGHT", emboss=False)
        header.operator(STS_OT_clear_results.bl_idname, text="", icon="X", emboss=False)
        if not settings.show_results:
            return
        if settings.results_info:
            layout.label(text=settings.results_info, icon="INFO")

        icons = {"OK": "CHECKMARK", "WARN": "ERROR", "ERROR": "CANCEL"}
        for item in settings.results:
            box = layout.box()
            row = box.row()
            row.alert = item.level == "ERROR"
            row.label(text=item.name, icon=icons[item.level])
            obj = context.scene.objects.get(item.name)
            if item.level != "OK" and obj and obj.type == "MESH":
                op = row.operator(STS_OT_show_problems.bl_idname, text="", icon="ZOOM_SELECTED")
                op.object_name = item.name
            col = box.column(align=True)
            col.scale_y = 0.8
            for line in item.text.split("\n"):
                col.label(text=line)


class STS_PT_slicer(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Slicer"
    bl_label = "Slicer"
    bl_parent_id = "STS_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        prefs = get_prefs(context)
        if prefs:
            draw_slicer_settings(self.layout, context, prefs)
        else:
            name, path = find_slicer(context)
            self.layout.label(text=path or f"{name} not found", icon="CHECKMARK" if path else "ERROR")


classes = (
    STS_Preferences,
    STS_CheckResult,
    STS_Settings,
    STS_OT_send,
    STS_OT_check,
    STS_OT_show_problems,
    STS_OT_clear_results,
    STS_PT_main,
    STS_PT_units,
    STS_PT_check,
    STS_PT_slicer,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.send_to_slicer = PointerProperty(type=STS_Settings)


def unregister():
    del bpy.types.Scene.send_to_slicer
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
