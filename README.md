# Send to Slicer

**Send your selected Blender objects to your 3D printing slicer in one click, with a built-in print check.**

<img src="docs/images/panel.png" alt="Send to Slicer panel in the Blender sidebar" align="right" width="300">

No more *File → Export → STL → find the folder → open the slicer → import*. Select your objects, click **Send to Slicer**, and they appear in your slicer, in millimeters and placed on the build plate.

- **One click**: exports the selected objects and opens them in your slicer
- **Many slicers**: Anycubic Slicer Next, OrcaSlicer, Bambu Studio, PrusaSlicer, UltiMaker Cura, or any custom program, auto-detected
- **3MF or STL**: 3MF keeps object names and units, STL works everywhere
- **One file or one file per object**
- **Apply modifiers** on export without touching your scene
- **Correct size**: converts your scene units to millimeters automatically
- **Print check**: finds holes, non-manifold edges, inside-out normals, self-intersections, wrong units and objects that don't fit on the build plate

<br clear="right">

## Requirements

- Blender **4.2** or newer (tested with 4.4 and 5.2)
- A slicer that opens files passed on the command line (all slicers listed above do)
- Tested on Windows. macOS and Linux should work, but are untested so far, so feedback is welcome.

## Installation

1. Download **`send_to_slicer-x.y.z.zip`** from the [latest release](../../releases/latest).
   > ⚠️ Don't use the green **Code → Download ZIP** button. That archive contains the whole repository and cannot be installed in Blender.
2. Drag the ZIP into the Blender window, **or** go to *Edit → Preferences → Get Extensions → ⌄ (top right) → Install from Disk…* and pick the ZIP.
3. Open the 3D Viewport sidebar with **N** and select the **Slicer** tab.

Step-by-step guide with troubleshooting: [docs/installation.md](docs/installation.md)

## Usage

1. Select one or more objects in Object Mode.
2. Choose the format (3MF/STL) and whether multiple objects go into one file or separate files.
3. Click **Send to Slicer**.

Optional: click **Check** under *Print Check* first to see whether your meshes are watertight and correctly sized.

Full guide with all options: [docs/usage.md](docs/usage.md)

## How it works

The add-on writes the selected objects (with modifiers applied, transformed into world space and converted to millimeters) into a temporary 3MF or STL file and starts the slicer with that file as a command line argument, the same way "Open with…" does. If your slicer is already running and set to allow only one instance, the file is loaded into the open window.

## Contributing

Bug reports and ideas are welcome, please use the [issue templates](../../issues/new/choose).
Want support for another slicer? Open a feature request with the slicer's name and install path.

Running the tests (requires Blender, no UI):

```bash
blender --background --factory-startup --python-exit-code 1 --python tests/run_tests.py
```

Building the installable ZIP locally:

```bash
python build.py
```

Releasing: bump `version` in `send_to_slicer/blender_manifest.toml`, add an entry to `CHANGELOG.md`, then push a tag like `v1.0.1`. GitHub Actions builds the ZIP and attaches it to the release.

## License

[GPL-3.0-or-later](LICENSE), like Blender itself.

*Send to Slicer is an independent project and is not affiliated with or endorsed by Anycubic, Bambu Lab, Prusa Research, UltiMaker or the OrcaSlicer project. All product names are trademarks of their respective owners.*
