# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-23

### Added
- One-click export of the selected objects to the slicer (sidebar tab **Slicer** in the 3D Viewport).
- Supported slicers: Anycubic Slicer Next, OrcaSlicer, Bambu Studio, PrusaSlicer, UltiMaker Cura, or any custom program. Auto-detection of installed slicers.
- Export as 3MF (millimeters, object names kept) or binary STL.
- Options: apply modifiers, one file or one file per object, place the selection on the build plate.
- Unit conversion from the scene's unit settings or a manual factor.
- Print check: open edges, non-manifold edges, inside-out or inconsistent normals, loose geometry, degenerate faces, self-intersections, size vs. build plate, suspiciously small or huge objects (wrong units).
- "Show problems" button that selects non-manifold edges in Edit Mode.
