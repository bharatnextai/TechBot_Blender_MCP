import hashlib
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def png_metadata(path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError(f"Not a PNG with an IHDR header: {path}")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    return data, width, height, bit_depth, color_type


class TestBrandingAssets(unittest.TestCase):
    def test_documentation_logo_preserves_uploaded_original_bytes(self):
        path = ROOT / "docs" / "assets" / "branding" / "TB81_Github_logo.png"
        data, width, height, bit_depth, color_type = png_metadata(path)
        self.assertEqual(hashlib.sha256(data).hexdigest(), "fae3211dfa7213f4a2f40a48dc87fa3e343f67336d4dafd8e1c9445cc73e96fb")
        self.assertEqual((width, height), (303, 319))
        self.assertEqual(color_type, 6)  # RGBA, retains transparency.
        self.assertEqual(bit_depth, 8)

    def test_blender_ui_logo_is_downsampled_rgba_png(self):
        path = ROOT / "blender_addon" / "universal_mcp" / "assets" / "techbot81_icon.png"
        _, width, height, bit_depth, color_type = png_metadata(path)
        self.assertEqual((width, height), (128, 135))
        self.assertEqual(color_type, 6)
        self.assertEqual(bit_depth, 8)


if __name__ == "__main__":
    unittest.main()
