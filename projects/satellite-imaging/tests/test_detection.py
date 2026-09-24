"""
Satellite Vision Intelligence Platform — Detection Unit Tests
==============================================================
Pure unit tests for image processing utilities used by the change-detection
pipeline.  These tests use synthetic numpy arrays — no model weights,
GPU, or network access required.

Run with:  pytest tests/test_detection.py -v
"""

import numpy as np
import pytest


# ===========================================================================
# Module-under-test helpers (self-contained so tests work standalone)
# ===========================================================================

def tile_image(image: np.ndarray, tile_size: int) -> list[np.ndarray]:
    """
    Split a (C, H, W) image into non-overlapping tiles of (C, tile_size, tile_size).
    If the image dimensions are not evenly divisible the right/bottom edges are
    padded with zeros.
    """
    c, h, w = image.shape
    pad_h = (tile_size - h % tile_size) % tile_size
    pad_w = (tile_size - w % tile_size) % tile_size
    if pad_h or pad_w:
        image = np.pad(image, ((0, 0), (0, pad_h), (0, pad_w)), mode="constant")
    _, h_pad, w_pad = image.shape
    tiles = []
    for y in range(0, h_pad, tile_size):
        for x in range(0, w_pad, tile_size):
            tiles.append(image[:, y : y + tile_size, x : x + tile_size])
    return tiles


def stitch_tiles(tiles: list[np.ndarray], orig_h: int, orig_w: int, tile_size: int) -> np.ndarray:
    """
    Reassemble a flat list of (C, tile_size, tile_size) tiles back into a
    (C, orig_h, orig_w) image, discarding any padding.
    """
    c = tiles[0].shape[0]
    cols = int(np.ceil(orig_w / tile_size))
    rows = int(np.ceil(orig_h / tile_size))
    full_h = rows * tile_size
    full_w = cols * tile_size
    canvas = np.zeros((c, full_h, full_w), dtype=tiles[0].dtype)
    idx = 0
    for r in range(rows):
        for col in range(cols):
            canvas[:, r * tile_size : (r + 1) * tile_size,
                      col * tile_size : (col + 1) * tile_size] = tiles[idx]
            idx += 1
    return canvas[:, :orig_h, :orig_w]


def compute_change_mask(before: np.ndarray, after: np.ndarray, threshold: float) -> np.ndarray:
    """
    Compute a binary change mask from two (C, H, W) images.
    1. Compute L2 distance across channels for each pixel.
    2. Normalize to [0, 1].
    3. Threshold.
    Returns a (H, W) uint8 mask where 1 = changed.
    """
    diff = np.linalg.norm(after.astype(np.float64) - before.astype(np.float64), axis=0)
    if diff.max() > 0:
        diff_norm = diff / diff.max()
    else:
        diff_norm = diff
    mask = (diff_norm >= threshold).astype(np.uint8)
    return mask


def compute_statistics(mask: np.ndarray) -> dict:
    """
    Compute summary statistics from a binary change mask (H, W).
    """
    total = mask.size
    changed = int(mask.sum())
    return {
        "total_pixels": total,
        "changed_pixels": changed,
        "unchanged_pixels": total - changed,
        "change_percentage": round(100.0 * changed / total, 4) if total > 0 else 0.0,
    }


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def rng():
    return np.random.default_rng(seed=12345)


@pytest.fixture
def sample_image(rng):
    """A (3, 128, 128) uint8 image."""
    return rng.integers(0, 256, size=(3, 128, 128), dtype=np.uint8)


@pytest.fixture
def identical_pair(sample_image):
    """Two identical images (no change)."""
    return sample_image.copy(), sample_image.copy()


@pytest.fixture
def shifted_pair(sample_image, rng):
    """Before/after where `after` has a bright square injected (simulating change)."""
    after = sample_image.copy()
    after[:, 32:64, 32:64] = 255  # inject bright block
    return sample_image, after


# ===========================================================================
# 1. Tiling
# ===========================================================================

class TestTiling:
    def test_exact_tile_count(self, sample_image):
        tiles = tile_image(sample_image, tile_size=64)
        # 128/64 = 2 rows * 2 cols = 4 tiles
        assert len(tiles) == 4
        assert all(t.shape == (3, 64, 64) for t in tiles)

    def test_non_divisible_dimensions(self, rng):
        img = rng.integers(0, 256, size=(3, 100, 100), dtype=np.uint8)
        tiles = tile_image(img, tile_size=64)
        # ceil(100/64) = 2 → 2*2 = 4 tiles
        assert len(tiles) == 4
        assert all(t.shape == (3, 64, 64) for t in tiles)

    def test_tile_size_larger_than_image(self, rng):
        img = rng.integers(0, 256, size=(3, 30, 30), dtype=np.uint8)
        tiles = tile_image(img, tile_size=64)
        assert len(tiles) == 1
        assert tiles[0].shape == (3, 64, 64)

    def test_single_band(self, rng):
        img = rng.integers(0, 256, size=(1, 128, 128), dtype=np.uint8)
        tiles = tile_image(img, tile_size=64)
        assert len(tiles) == 4
        assert tiles[0].shape[0] == 1


# ===========================================================================
# 2. Stitching
# ===========================================================================

class TestStitching:
    def test_roundtrip_exact(self, sample_image):
        """Tile then stitch should recover the original image exactly."""
        tiles = tile_image(sample_image, tile_size=64)
        stitched = stitch_tiles(tiles, 128, 128, tile_size=64)
        np.testing.assert_array_equal(stitched, sample_image)

    def test_roundtrip_padded(self, rng):
        """Tile+stitch with padding should recover original dimensions."""
        img = rng.integers(0, 256, size=(3, 100, 100), dtype=np.uint8)
        tiles = tile_image(img, tile_size=64)
        stitched = stitch_tiles(tiles, 100, 100, tile_size=64)
        assert stitched.shape == (3, 100, 100)
        np.testing.assert_array_equal(stitched, img)

    def test_stitch_preserves_dtype(self, rng):
        img = rng.integers(0, 256, size=(3, 64, 64), dtype=np.uint8)
        tiles = tile_image(img, tile_size=32)
        stitched = stitch_tiles(tiles, 64, 64, tile_size=32)
        assert stitched.dtype == np.uint8


# ===========================================================================
# 3. Change Mask Thresholding
# ===========================================================================

class TestChangeMask:
    def test_identical_images_no_change(self, identical_pair):
        before, after = identical_pair
        mask = compute_change_mask(before, after, threshold=0.1)
        assert mask.sum() == 0

    def test_all_change_at_zero_threshold(self, shifted_pair):
        """With threshold=0.0 and any non-zero diff, everything above 0 is flagged."""
        before, after = shifted_pair
        mask = compute_change_mask(before, after, threshold=0.0)
        # At minimum the injected block should show as changed
        assert mask.sum() > 0

    def test_known_change_region(self, shifted_pair):
        before, after = shifted_pair
        mask = compute_change_mask(before, after, threshold=0.3)
        # The injected block at [32:64, 32:64] should be flagged
        block = mask[32:64, 32:64]
        # Most of the block should be marked as changed
        assert block.sum() > 0.5 * block.size

    def test_high_threshold_reduces_change(self, shifted_pair):
        before, after = shifted_pair
        mask_low = compute_change_mask(before, after, threshold=0.2)
        mask_high = compute_change_mask(before, after, threshold=0.8)
        assert mask_high.sum() <= mask_low.sum()

    def test_mask_shape(self, shifted_pair):
        before, after = shifted_pair
        mask = compute_change_mask(before, after, threshold=0.5)
        # mask should be (H, W), not (C, H, W)
        assert mask.ndim == 2
        assert mask.shape == (128, 128)

    def test_mask_values_binary(self, shifted_pair):
        before, after = shifted_pair
        mask = compute_change_mask(before, after, threshold=0.5)
        unique = set(np.unique(mask))
        assert unique.issubset({0, 1})


# ===========================================================================
# 4. Statistics Computation
# ===========================================================================

class TestStatistics:
    def test_no_change(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        stats = compute_statistics(mask)
        assert stats["total_pixels"] == 10000
        assert stats["changed_pixels"] == 0
        assert stats["change_percentage"] == 0.0

    def test_full_change(self):
        mask = np.ones((100, 100), dtype=np.uint8)
        stats = compute_statistics(mask)
        assert stats["changed_pixels"] == 10000
        assert stats["change_percentage"] == 100.0

    def test_partial_change(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[:50, :] = 1  # half the image
        stats = compute_statistics(mask)
        assert stats["changed_pixels"] == 5000
        assert stats["change_percentage"] == 50.0

    def test_unchanged_plus_changed_equals_total(self):
        rng = np.random.default_rng(99)
        mask = rng.integers(0, 2, size=(200, 200), dtype=np.uint8)
        stats = compute_statistics(mask)
        assert stats["changed_pixels"] + stats["unchanged_pixels"] == stats["total_pixels"]

    def test_empty_mask(self):
        mask = np.zeros((0, 0), dtype=np.uint8)
        stats = compute_statistics(mask)
        assert stats["total_pixels"] == 0
        assert stats["change_percentage"] == 0.0
