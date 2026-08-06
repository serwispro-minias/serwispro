from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, time, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.service_order import ServiceOrder
from app.models.service_order_photo_annotation import PHOTO_ANNOTATION_PRIORITY_CHOICES, PHOTO_ANNOTATION_TYPE_CHOICES, PhotoAnnotation
from app.models.service_order_photo import SERVICE_ORDER_PHOTO_TYPE_CHOICES, SERVICE_ORDER_PHOTO_TYPE_LABELS, ServiceOrderPhoto

from .exceptions import ServiceOrderPhotoNotFoundError, ServiceOrderPhotoPermissionError, ServiceOrderPhotoValidationError
from .repository import ServiceOrderPhotoRepository


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
THUMBNAIL_MAX_SIZE = (480, 480)
IMAGE_MAX_SIZE = (2200, 2200)
COLOR_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class ServiceOrderPhotoService:
    def __init__(self, repository: ServiceOrderPhotoRepository | None = None) -> None:
        self.repository = repository or ServiceOrderPhotoRepository()

    def get_type_choices(self) -> list[tuple[str, str]]:
        return list(SERVICE_ORDER_PHOTO_TYPE_CHOICES)

    def get_type_labels(self) -> dict[str, str]:
        return dict(SERVICE_ORDER_PHOTO_TYPE_LABELS)

    def get_annotation_type_choices(self) -> list[tuple[str, str]]:
        return list(PHOTO_ANNOTATION_TYPE_CHOICES)

    def get_annotation_priority_choices(self) -> list[tuple[str, str]]:
        return list(PHOTO_ANNOTATION_PRIORITY_CHOICES)

    def author_choices(self, *, order_id: int, company_id: int, branch_id: int | None) -> list[tuple[int, str]]:
        return [(-1, "Wszyscy autorzy")] + self.repository.list_authors(order_id=order_id, company_id=company_id, branch_id=branch_id)

    def list_photos(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        photo_type: str | None,
        date_from: date | None,
        date_to: date | None,
        author_id: int | None,
    ) -> list[ServiceOrderPhoto]:
        order = self._get_scoped_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        date_from_dt = datetime.combine(date_from, time.min) if date_from else None
        date_to_dt = datetime.combine(date_to, time.max) if date_to else None
        return self.repository.list_photos(
            order_id=order.id,
            company_id=company_id,
            branch_id=branch_id,
            photo_type=photo_type,
            date_from=date_from_dt,
            date_to=date_to_dt,
            author_id=(None if author_id in (None, -1) else author_id),
        )

    def upload_photos(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        photo_type: str,
        title: str | None,
        description: str | None,
        taken_at: date | None,
        sort_order: int | None,
        is_visible_for_customer: bool,
        files: Iterable[FileStorage],
        main_photo_index: int | None,
        upload_root: Path,
    ) -> list[ServiceOrderPhoto]:
        self._ensure_add_permission()
        order = self._get_scoped_order(order_id=order_id, company_id=company_id, branch_id=branch_id)

        normalized_type = (photo_type or "").strip().upper()
        if normalized_type not in {value for value, _ in SERVICE_ORDER_PHOTO_TYPE_CHOICES}:
            raise ServiceOrderPhotoValidationError("Niepoprawny typ zdjęcia.")

        prepared = self._prepare_files(files)
        if not prepared:
            raise ServiceOrderPhotoValidationError("Wybierz co najmniej jedno zdjęcie.")

        photos_dir = upload_root / "service_orders" / str(order.id) / "photos"
        thumbs_dir = photos_dir / "thumbnails"
        photos_dir.mkdir(parents=True, exist_ok=True)
        thumbs_dir.mkdir(parents=True, exist_ok=True)

        created_rows: list[ServiceOrderPhoto] = []
        base_sort_order = 0 if (main_photo_index is not None and main_photo_index >= 0) else (sort_order or 100)

        for index, prepared_file in enumerate(prepared):
            ext = prepared_file["extension"]
            file_name = f"{uuid4().hex}{ext}"
            full_path = photos_dir / file_name
            thumb_path = thumbs_dir / f"{Path(file_name).stem}_thumb.webp"

            image = prepared_file["image"]
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            image.thumbnail(IMAGE_MAX_SIZE)

            self._save_image(image=image, target=full_path, extension=ext)

            thumb = image.copy()
            thumb.thumbnail(THUMBNAIL_MAX_SIZE)
            thumb.save(thumb_path, format="WEBP", quality=82, method=6)

            width, height = image.size
            taken_at_value = datetime.combine(taken_at, time.min) if taken_at else datetime.now(timezone.utc)
            effective_sort = base_sort_order + index
            if main_photo_index is not None and index == main_photo_index:
                effective_sort = 0

            row = self.repository.create_photo(
                {
                    "service_order_id": order.id,
                    "photo_type": normalized_type,
                    "title": (title or "").strip() or None,
                    "description": (description or "").strip() or None,
                    "file_name": file_name,
                    "original_file_name": prepared_file["original_name"],
                    "mime_type": prepared_file["mime_type"],
                    "file_size": int(full_path.stat().st_size),
                    "width": int(width),
                    "height": int(height),
                    "taken_at": taken_at_value,
                    "sort_order": int(effective_sort),
                    "is_visible_for_customer": bool(is_visible_for_customer),
                    "company_id": company_id,
                    "branch_id": order.branch_id,
                    "created_by": user_id,
                    "updated_by": user_id,
                }
            )
            created_rows.append(row)

        db.session.commit()
        return created_rows

    def delete_photo(self, *, photo_id: int, company_id: int, branch_id: int | None, upload_root: Path) -> ServiceOrderPhoto:
        self._ensure_delete_permission()
        row = self._get_scoped_photo(photo_id=photo_id, company_id=company_id, branch_id=branch_id)

        original_path, thumb_path = self.photo_file_paths(upload_root=upload_root, order_id=row.service_order_id, file_name=row.file_name)
        if original_path.exists() and original_path.is_file():
            original_path.unlink(missing_ok=True)
        if thumb_path.exists() and thumb_path.is_file():
            thumb_path.unlink(missing_ok=True)

        row.is_active = False
        row.deleted_at = datetime.now(timezone.utc)
        self.repository.save(row)
        db.session.commit()
        return row

    def get_photo(self, *, photo_id: int, company_id: int, branch_id: int | None) -> ServiceOrderPhoto:
        return self._get_scoped_photo(photo_id=photo_id, company_id=company_id, branch_id=branch_id)

    def list_annotations(
        self,
        *,
        photo_id: int,
        company_id: int,
        branch_id: int | None,
        for_customer: bool,
    ) -> list[PhotoAnnotation]:
        photo = self._get_scoped_photo(photo_id=photo_id, company_id=company_id, branch_id=branch_id)
        return self.repository.list_annotations(
            photo_id=photo.id,
            company_id=company_id,
            branch_id=branch_id,
            only_customer_visible=for_customer,
        )

    def create_annotation(
        self,
        *,
        photo_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        payload: dict[str, object],
    ) -> PhotoAnnotation:
        self._ensure_annotation_write_permission()
        photo = self._get_scoped_photo(photo_id=photo_id, company_id=company_id, branch_id=branch_id)
        clean = self._normalize_annotation_payload(payload)
        clean.update(
            {
                "photo_id": photo.id,
                "company_id": company_id,
                "branch_id": photo.branch_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        row = self.repository.create_annotation(clean)
        db.session.commit()
        return row

    def update_annotation(
        self,
        *,
        annotation_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        payload: dict[str, object],
    ) -> PhotoAnnotation:
        self._ensure_annotation_write_permission()
        row = self._get_scoped_annotation(annotation_id=annotation_id, company_id=company_id, branch_id=branch_id)
        clean = self._normalize_annotation_payload(payload)
        row.annotation_type = str(clean["annotation_type"])
        row.x = Decimal(str(clean["x"]))
        row.y = Decimal(str(clean["y"]))
        row.width = Decimal(str(clean["width"]))
        row.height = Decimal(str(clean["height"]))
        row.rotation = Decimal(str(clean["rotation"]))
        row.color = str(clean["color"])
        row.title = clean["title"]
        row.description = clean["description"]
        row.priority = str(clean["priority"])
        row.is_visible_for_customer = bool(clean["is_visible_for_customer"])
        row.points_json = clean["points_json"]
        row.updated_by = user_id
        self.repository.save_annotation(row)
        db.session.commit()
        return row

    def delete_annotation(
        self,
        *,
        annotation_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
    ) -> PhotoAnnotation:
        self._ensure_annotation_delete_permission()
        row = self._get_scoped_annotation(annotation_id=annotation_id, company_id=company_id, branch_id=branch_id)
        row.is_active = False
        row.deleted_at = datetime.now(timezone.utc)
        row.deleted_by = user_id
        self.repository.save_annotation(row)
        db.session.commit()
        return row

    def annotation_to_dict(self, row: PhotoAnnotation) -> dict[str, object]:
        return {
            "id": row.id,
            "photo_id": row.photo_id,
            "annotation_type": row.annotation_type,
            "x": float(row.x),
            "y": float(row.y),
            "width": float(row.width),
            "height": float(row.height),
            "rotation": float(row.rotation),
            "color": row.color,
            "title": row.title or "",
            "description": row.description or "",
            "priority": row.priority,
            "is_visible_for_customer": bool(row.is_visible_for_customer),
            "points_json": row.points_json or "",
        }

    def render_annotated_photo_bytes(
        self,
        *,
        photo: ServiceOrderPhoto,
        upload_root: Path,
        company_id: int,
        branch_id: int | None,
        customer_only: bool,
    ) -> bytes | None:
        original = self.resolve_original_path(upload_root=upload_root, photo=photo)
        annotations = self.repository.list_annotations(
            photo_id=photo.id,
            company_id=company_id,
            branch_id=branch_id,
            only_customer_visible=customer_only,
        )
        if not annotations:
            return None

        image = Image.open(original)
        image = ImageOps.exif_transpose(image).convert("RGB")
        draw = ImageDraw.Draw(image)
        image_w, image_h = image.size

        for row in annotations:
            self._draw_annotation(draw=draw, row=row, image_w=image_w, image_h=image_h)

        out = BytesIO()
        image.save(out, format="JPEG", quality=88, optimize=True)
        return out.getvalue()

    def protocol_photos(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        photo_ids: list[int] | None,
        default_types: set[str],
    ) -> list[ServiceOrderPhoto]:
        rows = self.list_photos(
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            photo_type=None,
            date_from=None,
            date_to=None,
            author_id=None,
        )
        if photo_ids:
            id_set = set(photo_ids)
            return [row for row in rows if row.id in id_set]
        return [row for row in rows if row.photo_type in default_types]

    def photo_file_paths(self, *, upload_root: Path, order_id: int, file_name: str) -> tuple[Path, Path]:
        photos_dir = upload_root / "service_orders" / str(order_id) / "photos"
        original = photos_dir / file_name
        thumb = photos_dir / "thumbnails" / f"{Path(file_name).stem}_thumb.webp"
        return original, thumb

    def resolve_original_path(self, *, upload_root: Path, photo: ServiceOrderPhoto) -> Path:
        original, _ = self.photo_file_paths(upload_root=upload_root, order_id=photo.service_order_id, file_name=photo.file_name)
        if not original.exists() or not original.is_file():
            raise ServiceOrderPhotoNotFoundError("Plik zdjęcia nie istnieje.")
        return original

    def resolve_thumbnail_path(self, *, upload_root: Path, photo: ServiceOrderPhoto) -> Path:
        original, thumb = self.photo_file_paths(upload_root=upload_root, order_id=photo.service_order_id, file_name=photo.file_name)
        if thumb.exists() and thumb.is_file():
            return thumb
        if not original.exists() or not original.is_file():
            raise ServiceOrderPhotoNotFoundError("Miniatura i oryginał nie istnieją.")
        return original

    def _prepare_files(self, files: Iterable[FileStorage]) -> list[dict[str, object]]:
        prepared: list[dict[str, object]] = []
        for item in files:
            if item is None:
                continue
            original_name = secure_filename((item.filename or "").strip())
            if not original_name:
                continue

            extension = Path(original_name).suffix.lower()
            if extension not in ALLOWED_EXTENSIONS:
                raise ServiceOrderPhotoValidationError("Dozwolone formaty: jpg, jpeg, png, webp.")

            raw = item.read()
            item.stream.seek(0)
            if not raw:
                continue
            if len(raw) > MAX_UPLOAD_SIZE_BYTES:
                raise ServiceOrderPhotoValidationError("Maksymalny rozmiar pojedynczego pliku to 10 MB.")

            try:
                image = Image.open(BytesIO(raw))
                image.verify()
                image = Image.open(BytesIO(raw))
            except UnidentifiedImageError as exc:
                raise ServiceOrderPhotoValidationError("Plik nie jest poprawnym obrazem.") from exc

            detected_mime = Image.MIME.get(image.format or "", "").lower()
            if detected_mime not in ALLOWED_MIME:
                raise ServiceOrderPhotoValidationError("Nieprawidłowy typ MIME obrazu.")

            prepared.append(
                {
                    "original_name": original_name,
                    "extension": self._normalize_extension(extension=extension, detected_mime=detected_mime),
                    "mime_type": detected_mime,
                    "image": image,
                }
            )

        return prepared

    def _normalize_extension(self, *, extension: str, detected_mime: str) -> str:
        if detected_mime == "image/jpeg":
            return ".jpg"
        if detected_mime == "image/png":
            return ".png"
        if detected_mime == "image/webp":
            return ".webp"
        return extension

    def _save_image(self, *, image: Image.Image, target: Path, extension: str) -> None:
        if extension == ".png":
            image.save(target, format="PNG", optimize=True)
            return
        if extension == ".webp":
            image.save(target, format="WEBP", quality=84, method=6)
            return
        image.save(target, format="JPEG", quality=86, optimize=True, progressive=True)

    def _get_scoped_order(self, *, order_id: int, company_id: int, branch_id: int | None) -> ServiceOrder:
        row = self.repository.get_order(order_id=order_id, company_id=company_id)
        if row is None:
            raise ServiceOrderPhotoNotFoundError("Nie znaleziono zlecenia.")
        self._ensure_branch_scope(order_branch_id=row.branch_id, branch_id=branch_id)
        return row

    def _get_scoped_photo(self, *, photo_id: int, company_id: int, branch_id: int | None) -> ServiceOrderPhoto:
        row = self.repository.get_photo(photo_id=photo_id, company_id=company_id, branch_id=branch_id)
        if row is None:
            raise ServiceOrderPhotoNotFoundError("Nie znaleziono zdjęcia.")
        self._ensure_branch_scope(order_branch_id=row.branch_id, branch_id=branch_id)
        return row

    def _ensure_branch_scope(self, *, order_branch_id: int | None, branch_id: int | None) -> None:
        if branch_id is None and order_branch_id is None:
            return
        if branch_id is None and order_branch_id is not None:
            raise ServiceOrderPhotoPermissionError("Brak dostępu do oddziału.")
        if branch_id is not None and order_branch_id != branch_id:
            raise ServiceOrderPhotoPermissionError("Brak dostępu do oddziału.")

    def _role_names(self) -> set[str]:
        from flask_login import current_user

        try:
            return {(role.name or "").strip().lower() for role in getattr(current_user, "roles", [])}
        except OperationalError:
            return set()

    def _ensure_add_permission(self) -> None:
        names = self._role_names()
        if not names:
            return
        if names.intersection({"technik", "operator", "kierownik", "administrator"}):
            return
        raise ServiceOrderPhotoPermissionError("Brak uprawnień do dodawania zdjęć.")

    def _ensure_delete_permission(self) -> None:
        names = self._role_names()
        if not names:
            return
        if names.intersection({"operator", "administrator"}):
            return
        raise ServiceOrderPhotoPermissionError("Brak uprawnień do usuwania zdjęć.")

    def _get_scoped_annotation(self, *, annotation_id: int, company_id: int, branch_id: int | None) -> PhotoAnnotation:
        row = self.repository.get_annotation(annotation_id=annotation_id, company_id=company_id, branch_id=branch_id)
        if row is None or row.photo is None:
            raise ServiceOrderPhotoNotFoundError("Nie znaleziono oznaczenia.")
        self._ensure_branch_scope(order_branch_id=row.branch_id, branch_id=branch_id)
        return row

    def _ensure_annotation_write_permission(self) -> None:
        names = self._role_names()
        if not names:
            return
        if names.intersection({"technik", "operator", "kierownik", "administrator"}):
            return
        raise ServiceOrderPhotoPermissionError("Brak uprawnień do edycji oznaczeń.")

    def _ensure_annotation_delete_permission(self) -> None:
        names = self._role_names()
        if not names:
            return
        if names.intersection({"operator", "administrator"}):
            return
        raise ServiceOrderPhotoPermissionError("Brak uprawnień do usuwania oznaczeń.")

    def _normalize_annotation_payload(self, payload: dict[str, object]) -> dict[str, object]:
        annotation_type = str(payload.get("annotation_type") or "").strip().upper()
        if annotation_type not in {value for value, _ in PHOTO_ANNOTATION_TYPE_CHOICES}:
            raise ServiceOrderPhotoValidationError("Niepoprawny typ oznaczenia.")

        x = self._normalize_decimal(payload.get("x"), "x")
        y = self._normalize_decimal(payload.get("y"), "y")
        width = self._normalize_decimal(payload.get("width", 0), "width")
        height = self._normalize_decimal(payload.get("height", 0), "height")
        rotation = self._normalize_decimal(payload.get("rotation", 0), "rotation")

        if x < 0 or x > 1 or y < 0 or y > 1:
            raise ServiceOrderPhotoValidationError("Wspolrzedne x/y musza byc w zakresie 0..1.")
        if width < 0 or width > 2 or height < 0 or height > 2:
            raise ServiceOrderPhotoValidationError("Szerokosc i wysokosc musza byc dodatnie.")
        if rotation < -360 or rotation > 360:
            raise ServiceOrderPhotoValidationError("Rotacja musi byc w zakresie -360..360.")

        color = str(payload.get("color") or "").strip()
        if not COLOR_HEX_RE.match(color):
            raise ServiceOrderPhotoValidationError("Kolor musi byc w formacie #RRGGBB.")

        priority = str(payload.get("priority") or "NORMAL").strip().upper()
        if priority not in {value for value, _ in PHOTO_ANNOTATION_PRIORITY_CHOICES}:
            raise ServiceOrderPhotoValidationError("Niepoprawny priorytet oznaczenia.")

        points_json = str(payload.get("points_json") or "").strip() or None
        if points_json:
            self._validate_points_json(points_json)

        return {
            "annotation_type": annotation_type,
            "x": float(x),
            "y": float(y),
            "width": float(width),
            "height": float(height),
            "rotation": float(rotation),
            "color": color,
            "title": (str(payload.get("title") or "").strip() or None),
            "description": (str(payload.get("description") or "").strip() or None),
            "priority": priority,
            "is_visible_for_customer": self._as_bool(payload.get("is_visible_for_customer")),
            "points_json": points_json,
        }

    def _normalize_decimal(self, raw: object, field_name: str) -> Decimal:
        try:
            return Decimal(str(raw if raw is not None else 0))
        except Exception as exc:
            raise ServiceOrderPhotoValidationError(f"Niepoprawna wartosc pola {field_name}.") from exc

    def _validate_points_json(self, points_json: str) -> None:
        try:
            parsed = json.loads(points_json)
        except json.JSONDecodeError as exc:
            raise ServiceOrderPhotoValidationError("Niepoprawne dane punktow adnotacji.") from exc

        if not isinstance(parsed, list):
            raise ServiceOrderPhotoValidationError("Punkty adnotacji musza byc lista.")
        for point in parsed:
            if not isinstance(point, dict):
                raise ServiceOrderPhotoValidationError("Kazdy punkt adnotacji musi byc obiektem.")
            px = self._normalize_decimal(point.get("x", 0), "points.x")
            py = self._normalize_decimal(point.get("y", 0), "points.y")
            if px < 0 or px > 1 or py < 0 or py > 1:
                raise ServiceOrderPhotoValidationError("Wspolrzedne punktow musza byc w zakresie 0..1.")

    def _draw_annotation(self, *, draw: ImageDraw.ImageDraw, row: PhotoAnnotation, image_w: int, image_h: int) -> None:
        x = float(row.x) * image_w
        y = float(row.y) * image_h
        w = max(float(row.width) * image_w, 2)
        h = max(float(row.height) * image_h, 2)
        color = row.color or "#ff3b30"
        annotation_type = (row.annotation_type or "").upper()

        if annotation_type == "PIN":
            r = max(5, int(min(image_w, image_h) * 0.01))
            draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=color, outline="#ffffff", width=2)
        elif annotation_type == "CIRCLE":
            draw.ellipse([(x, y), (x + w, y + h)], outline=color, width=4)
        elif annotation_type == "RECTANGLE":
            draw.rectangle([(x, y), (x + w, y + h)], outline=color, width=4)
        elif annotation_type in {"ARROW", "LINE"}:
            points = self._parse_points(row.points_json)
            if len(points) >= 2:
                p1 = (points[0][0] * image_w, points[0][1] * image_h)
                p2 = (points[1][0] * image_w, points[1][1] * image_h)
            else:
                p1 = (x, y)
                p2 = (x + w, y + h)
            draw.line([p1, p2], fill=color, width=4)
            if annotation_type == "ARROW":
                self._draw_arrow_head(draw=draw, start=p1, end=p2, color=color)
        elif annotation_type == "POLYGON":
            points = self._parse_points(row.points_json)
            if len(points) >= 3:
                scaled = [(point[0] * image_w, point[1] * image_h) for point in points]
                draw.polygon(scaled, outline=color, width=3)
        elif annotation_type in {"TEXT", "NUMBER"}:
            text = row.title or row.description or ("#" if annotation_type == "NUMBER" else "TXT")
            draw.text((x, y), text, fill=color)

    def _parse_points(self, points_json: str | None) -> list[tuple[float, float]]:
        if not points_json:
            return []
        try:
            parsed = json.loads(points_json)
        except json.JSONDecodeError:
            return []
        points: list[tuple[float, float]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                px = float(item.get("x", 0))
                py = float(item.get("y", 0))
            except (TypeError, ValueError):
                continue
            points.append((px, py))
        return points

    def _draw_arrow_head(
        self,
        *,
        draw: ImageDraw.ImageDraw,
        start: tuple[float, float],
        end: tuple[float, float],
        color: str,
    ) -> None:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)
        if length < 1:
            return
        ux = dx / length
        uy = dy / length
        size = 12
        left = (end[0] - ux * size - uy * (size * 0.5), end[1] - uy * size + ux * (size * 0.5))
        right = (end[0] - ux * size + uy * (size * 0.5), end[1] - uy * size - ux * (size * 0.5))
        draw.polygon([end, left, right], fill=color)

    def _as_bool(self, raw: object) -> bool:
        if isinstance(raw, bool):
            return raw
        if raw is None:
            return False
        value = str(raw).strip().lower()
        return value in {"1", "true", "yes", "y", "on"}
