"""Smoke tests for the print check and the exporters.

Run with Blender (no UI needed):
    blender --background --factory-startup --python-exit-code 1 --python tests/run_tests.py
"""

import os
import pathlib
import sys
import tempfile
import zipfile

import bmesh
import bpy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import send_to_slicer as sts  # noqa: E402

sts.register()
ctx = bpy.context
scene = ctx.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 0.001  # 1 BU = 1 mm
settings = scene.send_to_slicer
failures = []


def make_cube(name, size=10.0, edit=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    if edit:
        edit(bm)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob


def first_face(bm):
    bm.faces.ensure_lookup_table()
    return bm.faces[0]


def overlapping(bm):
    r = bmesh.ops.create_cube(bm, size=10.0)
    bmesh.ops.translate(bm, verts=r["verts"], vec=(5, 5, 5))


cases = {
    "ok": (make_cube("ok"), "OK", None),
    "hole": (make_cube("hole", edit=lambda bm: bm.faces.remove(first_face(bm))), "ERROR", "open edges"),
    "inside_out": (make_cube("inside_out", edit=lambda bm: bmesh.ops.reverse_faces(bm, faces=bm.faces[:])),
                   "ERROR", "inwards"),
    "one_flipped": (make_cube("one_flipped", edit=lambda bm: bmesh.ops.reverse_faces(bm, faces=[first_face(bm)])),
                    "WARN", "inconsistent"),
    "tiny": (make_cube("tiny", size=0.1), "ERROR", "Very small"),
    "huge": (make_cube("huge", size=10000.0), "ERROR", "Huge"),
    "too_big": (make_cube("too_big", size=300.0), "WARN", "build plate"),
    "self_intersect": (make_cube("self_intersect", edit=overlapping), "WARN", "intersect"),
}
neg = make_cube("negative_scale")
neg.scale = (-1, 1, 1)
cases["negative_scale"] = (neg, "OK", None)

ctx.view_layer.update()
depsgraph = ctx.evaluated_depsgraph_get()
factor = sts.mm_factor(scene, settings)

for name, (obj, want_level, want_text) in cases.items():
    level, msgs = sts.analyse_object(obj, depsgraph, settings, factor)
    text = "\n".join(msgs)
    if level != want_level or (want_text and want_text not in text):
        failures.append(f"{name}: expected {want_level} / '{want_text}', got {level}:\n{text}")

# --- export ---
for o in scene.objects:
    o.select_set(o.name in {"ok", "negative_scale"})
export_dir = tempfile.mkdtemp(prefix="sts_test_")
sts.default_export_dir = lambda: export_dir  # not installed as add-on -> no preferences, default dir is used

for fmt in ("3MF", "STL"):
    for mode, expected in (("SINGLE", 1), ("SEPARATE", 2)):
        settings.file_format, settings.file_mode = fmt, mode
        files = sts.export_files(ctx)
        if len(files) != expected or not all(os.path.getsize(f) > 0 for f in files):
            failures.append(f"export {fmt}/{mode}: got {files}")

settings.file_format, settings.file_mode = "3MF", "SINGLE"
with zipfile.ZipFile(sts.export_files(ctx)[0]) as zf:
    model = zf.read("3D/3dmodel.model").decode()
    if 'unit="millimeter"' not in model or model.count("<object ") != 2:
        failures.append("3MF: wrong unit or object count")

settings.file_format = "STL"
stl = sts.export_files(ctx)[0]
if os.path.getsize(stl) != 84 + 50 * 24:  # 2 cubes x 12 triangles
    failures.append(f"STL: unexpected size {os.path.getsize(stl)}")

sts.unregister()

if failures:
    print("\n".join(["FAILED:"] + failures))
    sys.exit(1)
print(f"All {len(cases)} check cases and export tests passed.")
