"""Waveshare 13.3inch e-Paper HAT (K) hardware adapter.

Target panel: Waveshare 13.3inch e-Paper HAT (K), 960x680, black/white.
The low-level driver comes from Waveshare's official ``waveshare_epd`` package.

For now this adapter deliberately uses full refreshes only. Waveshare's
partial-refresh sequence assumes that the panel RAM has first been primed with
``display_Base()`` in the same powered session. Our dashboard currently runs as
short-lived cron processes, so cross-process partial refreshes are not enabled
until they have been verified on the real panel.
"""
from pathlib import Path

from PIL import Image

_CUR_IMG_PATH = Path("cache/cur_display_13in3.png")
EXPECTED_SIZE = (960, 680)


class EPaper13in3Display:
    """Display adapter for Waveshare 13.3inch e-Paper HAT (K)."""

    model = "waveshare_13in3k"
    supports_partials = False

    @staticmethod
    def _driver_module():
        try:
            from waveshare_epd import epd13in3k
        except ImportError as exc:
            raise RuntimeError(
                "Waveshare 13.3inch driver is not installed. "
                "On the Raspberry Pi run: "
                "venv/bin/pip install -r requirements-pi-13in3.txt"
            ) from exc
        return epd13in3k

    @staticmethod
    def _prepare(image: Image.Image) -> Image.Image:
        if image.size != EXPECTED_SIZE:
            raise RuntimeError(
                f"Waveshare 13.3inch (K) requires a 960x680 image, got "
                f"{image.size[0]}x{image.size[1]}"
            )
        return image.convert("1")

    @staticmethod
    def _save_cur(image: Image.Image):
        _CUR_IMG_PATH.parent.mkdir(parents=True, exist_ok=True)
        image.convert("1").save(_CUR_IMG_PATH)

    def _refresh(self, image: Image.Image, prime_base: bool = False):
        """Refresh the complete panel and power the HAT down afterwards."""
        driver = self._driver_module()
        image = self._prepare(image)
        epd = None
        try:
            epd = driver.EPD()
            epd.init()
            buffer = epd.getbuffer(image)
            if prime_base:
                # Writes both current and previous frame RAM. Use this for the
                # explicit full-refresh path and before future partial testing.
                epd.display_Base(buffer)
            else:
                epd.display(buffer)
            self._save_cur(image)
        finally:
            if epd is not None:
                try:
                    # Waveshare's sleep() also closes SPI/power via module_exit().
                    epd.sleep()
                except Exception:
                    try:
                        driver.epdconfig.module_exit()
                    except Exception:
                        # Do not mask the original display error during cleanup.
                        pass

    def show(self, image, **_kwargs):
        """Normal complete-panel refresh."""
        self._refresh(image, prime_base=False)

    def show_full(self, image, **_kwargs):
        """Complete refresh that also primes both panel frame buffers."""
        self._refresh(image, prime_base=True)

    def show_partials(self, regions, **_kwargs):
        raise RuntimeError(
            "Partial refresh is intentionally disabled for waveshare_13in3k "
            "until it has been verified on the physical panel."
        )
