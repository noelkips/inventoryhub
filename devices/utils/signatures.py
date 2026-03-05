import base64
from io import BytesIO

from PIL import Image


def _to_png_bytes(signature: str) -> bytes:
    """
    Accepts a base64 PNG data URL or raw base64; returns PNG bytes.
    """
    if not signature:
        return b""
    sig = signature.strip()
    if not sig:
        return b""
    if "," in sig and sig.lower().startswith("data:"):
        sig = sig.split(",", 1)[1]
    return base64.b64decode(sig)


def _to_data_url(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def normalize_signature_data_url(
    signature: str,
    *,
    canvas_width: int = 900,
    canvas_height: int = 300,
    padding: int = 18,
    white_threshold: int = 245,
) -> str:
    """
    Normalizes a signature image so that:
    - whitespace is trimmed,
    - signature is scaled up/down to fit a fixed-size canvas,
    - output is a PNG data URL.

    This makes signatures consistent in the generated PDF regardless of how big/small the user signed.
    """
    try:
        raw = _to_png_bytes(signature)
        if not raw:
            return ""

        img = Image.open(BytesIO(raw)).convert("RGBA")
        gray = img.convert("L")

        # Build a mask of "ink" pixels (anything darker than the threshold).
        # 255 = ink, 0 = background
        mask = gray.point(lambda p: 255 if p < white_threshold else 0)
        bbox = mask.getbbox()
        if not bbox:
            # nothing drawn
            return _to_data_url(raw)

        left, top, right, bottom = bbox
        left = max(left - padding, 0)
        top = max(top - padding, 0)
        right = min(right + padding, img.width)
        bottom = min(bottom + padding, img.height)

        cropped = img.crop((left, top, right, bottom))

        target_w = max(canvas_width, 1)
        target_h = max(canvas_height, 1)
        inner_w = max(target_w - padding * 2, 1)
        inner_h = max(target_h - padding * 2, 1)

        # Resize to fit (preserve aspect ratio)
        scale = min(inner_w / cropped.width, inner_h / cropped.height)
        new_w = max(int(cropped.width * scale), 1)
        new_h = max(int(cropped.height * scale), 1)
        resized = cropped.resize((new_w, new_h), Image.LANCZOS)

        # Paste centered on white background
        out = Image.new("RGBA", (target_w, target_h), (255, 255, 255, 255))
        x = (target_w - new_w) // 2
        y = (target_h - new_h) // 2
        out.paste(resized, (x, y), resized)

        buf = BytesIO()
        out.convert("RGB").save(buf, format="PNG", optimize=True)
        return _to_data_url(buf.getvalue())
    except Exception:
        # Best-effort: never break signing if normalization fails.
        return signature or ""

