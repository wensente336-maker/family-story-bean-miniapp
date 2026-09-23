from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


class CoverValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessedCover:
    main: bytes
    thumbnail: bytes
    width: int
    height: int
    sha256: str
    media_type: str = "image/webp"


class PodcastCoverProcessor:
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    max_bytes = 5 * 1024 * 1024
    main_size = (1200, 1200)
    thumbnail_size = (320, 320)

    def process(
        self, content: bytes, media_type: str, focal_x: float = 0.5, focal_y: float = 0.5
    ) -> ProcessedCover:
        if media_type not in self.allowed_types:
            raise CoverValidationError("仅支持 JPG、PNG 或 WebP 图片")
        if not content:
            raise CoverValidationError("封面图片为空")
        if len(content) > self.max_bytes:
            raise CoverValidationError("封面图片不能超过 5MB")
        try:
            with Image.open(BytesIO(content)) as probe:
                detected_format = probe.format
                probe.verify()
            if detected_format not in {"JPEG", "PNG", "WEBP"}:
                raise CoverValidationError("图片真实编码必须是 JPG、PNG 或 WebP")
            with Image.open(BytesIO(content)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
        except CoverValidationError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise CoverValidationError("图片文件已损坏或格式不匹配") from exc
        if image.width < 64 or image.height < 64:
            raise CoverValidationError("封面图片至少需要 64×64 像素")
        focal_x = min(1.0, max(0.0, focal_x))
        focal_y = min(1.0, max(0.0, focal_y))
        # Re-crop from the decoded source so subclasses may request a different
        # aspect ratio without stretching pixels.
        target_ratio = self.main_size[0] / self.main_size[1]
        source_ratio = image.width / image.height
        if source_ratio > target_ratio:
            crop_height = image.height
            crop_width = round(crop_height * target_ratio)
        else:
            crop_width = image.width
            crop_height = round(crop_width / target_ratio)
        left = round(min(image.width - crop_width, max(0, focal_x * image.width - crop_width / 2)))
        top = round(min(image.height - crop_height, max(0, focal_y * image.height - crop_height / 2)))
        crop = image.crop((left, top, left + crop_width, top + crop_height))
        main_image = ImageOps.fit(crop, self.main_size, Image.Resampling.LANCZOS)
        thumb_image = ImageOps.fit(crop, self.thumbnail_size, Image.Resampling.LANCZOS)
        main_buffer, thumb_buffer = BytesIO(), BytesIO()
        # Saving freshly decoded pixels without exif= strips EXIF, GPS and comments.
        main_image.save(main_buffer, "WEBP", quality=88, method=6)
        thumb_image.save(thumb_buffer, "WEBP", quality=82, method=6)
        main = main_buffer.getvalue()
        return ProcessedCover(
            main=main,
            thumbnail=thumb_buffer.getvalue(),
            width=self.main_size[0],
            height=self.main_size[1],
            sha256=hashlib.sha256(main).hexdigest(),
        )


class SoundPostcardCoverProcessor(PodcastCoverProcessor):
    main_size = (1200, 1600)
    thumbnail_size = (360, 480)
