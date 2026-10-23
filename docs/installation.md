# Installation

## 1. Download

Go to the [Releases page](../../../releases/latest) and download the file **`send_to_slicer-x.y.z.zip`** under *Assets*.

> ⚠️ Don't use the green **Code → Download ZIP** button on the main page and don't unpack the ZIP. Blender needs the release ZIP exactly as it is.

## 2. Install in Blender (4.2 or newer)

**Option A: drag & drop**
Drag the ZIP file from your file manager into the Blender window and confirm with **Install**.

**Option B: preferences**
1. *Edit → Preferences → Get Extensions*
2. Click the **⌄** arrow in the top right corner → **Install from Disk…**
3. Select the ZIP file and click **Install from Disk**.

The add-on is enabled automatically after installation.

## 3. Check the slicer

1. In *Edit → Preferences → Add-ons*, find **Send to Slicer** and expand it.
2. **Slicer** is set to *Auto-detect* by default. The line below shows which program was found.
3. If your slicer is not found, choose it from the list or pick **Custom program** and select the executable:

| Slicer | Typical location on Windows |
|---|---|
| Anycubic Slicer Next | `C:\Program Files\AnycubicSlicerNext\AnycubicSlicerNext.exe` |
| OrcaSlicer | `C:\Program Files\OrcaSlicer\orca-slicer.exe` |
| Bambu Studio | `C:\Program Files\Bambu Studio\bambu-studio.exe` |
| PrusaSlicer | `C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer.exe` |
| UltiMaker Cura | `C:\Program Files\UltiMaker Cura 5.x.x\UltiMaker-Cura.exe` |

On **macOS** select the `.app` in `/Applications`. On **Linux** the add-on looks for the slicer command on your `PATH` and for AppImages in `~/Applications`. Otherwise pick the AppImage as custom program.

## 4. Open the panel

In the 3D Viewport press **N** to open the sidebar and click the **Slicer** tab.

## Updating

Install the new ZIP the same way. Blender replaces the old version. Restart Blender afterwards to be safe.

## Uninstalling

*Edit → Preferences → Add-ons → Send to Slicer → ⌄ → Uninstall.*
Temporary export files are stored in your system's temp folder (`blender_send_to_slicer`) and can be deleted at any time.

## Troubleshooting

**"… not found"** in the panel
The slicer is not installed in a standard location. Choose *Custom program* in the add-on preferences and select the executable.

**A new slicer window opens every time**
Enable single-instance mode in your slicer's preferences. In OrcaSlicer-based slicers (Anycubic Slicer Next, OrcaSlicer, Bambu Studio) this setting is usually called something like *"Allow only one instance"*; the exact name differs between slicers.

**The model is 1000× too small or too large**
Open *Units & Build Plate* in the panel. With *From Scene*, the add-on uses *Scene Properties → Units → Unit Scale*. If your model was built "1 Blender unit = 1 mm" without setting the unit scale, switch to *Manual* and set `1 BU = 1 mm`. The *Print Check* warns about suspicious sizes.

**The add-on doesn't appear after installation**
Make sure you installed the release ZIP (not the source code ZIP) and that you use Blender 4.2 or newer. Check *Window → Toggle System Console* (Windows) for error messages and [open an issue](../../../issues/new/choose).
