# Owner-approved Launcher artwork

The owner supplied `ChatGPT Image 2026年9月10日 21_46_47.png` from Downloads on
2026-09-10 and explicitly requested the Launcher background, a white/blue palette
and the girl's portrait as the EXE icon. `background.png` is that original image,
copied without alteration. The original Downloads file is unchanged.

`portrait.png` was derived from that supplied image using imagegen, preserving the
girl's appearance on an opaque pale blue background. `studio.ico` packages the
approved portrait at 16, 24, 32, 48, 64, 128 and 256 pixels. Rebuild that format
with `scripts/build_studio_icon.py`; it does not generate new artwork.

These are static Launcher/application identity resources. Functional product
icons retain the original approved Lucide geometry. The Panel theme is unchanged.
