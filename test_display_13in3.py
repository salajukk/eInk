#!/usr/bin/env python3
"""Minimal hardware smoke test for Waveshare 13.3inch e-Paper HAT (K)."""

from PIL import Image, ImageDraw, ImageFont

from display.epaper_13in3 import EPaper13in3Display

WIDTH, HEIGHT = 960, 680


def main():
    image = Image.new("1", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    draw.rectangle((12, 12, WIDTH - 13, HEIGHT - 13), outline=0, width=4)
    draw.text((40, 45), "PERHEEN NAYTTO - 13.3in HARDWARE TEST", font=font, fill=0)
    draw.text((40, 85), "960 x 680 / Waveshare 13.3inch e-Paper HAT (K)", font=font, fill=0)
    draw.text((40, 125), "Jos tama teksti nakyy, SPI + ajuri + naytto toimivat.", font=font, fill=0)

    display = EPaper13in3Display()
    display.show_full(image)
    print("13.3inch e-Paper hardware test completed.")


if __name__ == "__main__":
    main()
