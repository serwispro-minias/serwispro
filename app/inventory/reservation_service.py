from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models.inventory_part import InventoryPart
from app.models.inventory_reservation import InventoryReservation, InventoryReservationStatusEnum
from app.models.service_order import ServiceOrder


@dataclass(slots=True)
class InventoryReservationResult:
    reservation: InventoryReservation | None
    reserved_quantity: Decimal
    missing_quantity: Decimal
    purchase_request: Any | None = None
    message: str | None = None


class InventoryReservationService:
    def reserve_for_order(
        self,
        *,
        inventory_item: InventoryPart,
        service_order: ServiceOrder,
        quantity: Decimal,
        user_id: int | None,
        company_id: int,
        branch_id: int | None,
    ) -> InventoryReservationResult:
        quantity = Decimal(quantity)
        if quantity <= Decimal("0"):
            raise ValueError("Ilość rezerwacji musi być większa od zera.")

        available = Decimal(inventory_item.quantity_available)
        reserved_quantity = min(quantity, available)
        missing_quantity = max(Decimal("0"), quantity - reserved_quantity)

        if available <= Decimal("0"):
            reservation = None
            self._record_history(
                inventory_item=inventory_item,
                service_order=service_order,
                quantity=quantity,
                operation_type="AUTO_PURCHASE_REQUEST",
                user_id=user_id,
                company_id=company_id,
                branch_id=branch_id,
            )
            return InventoryReservationResult(
                reservation=None,
                reserved_quantity=Decimal("0"),
                missing_quantity=quantity,
                purchase_request=None,
                message="Stan magazynowy wynosi 0. Część została automatycznie dodana do zakupów.",
            )

        if reserved_quantity > Decimal("0"):
            reservation = InventoryReservation(
                inventory_item_id=inventory_item.id,
                service_order_id=service_order.id,
                quantity=reserved_quantity,
                reserved_by=user_id,
                reserved_at=datetime.now(timezone.utc),
                status=InventoryReservationStatusEnum.RESERVED.value,
                company_id=company_id,
                branch_id=branch_id,
                created_by=user_id,
                updated_by=user_id,
            )
            db.session.add(reservation)
            db.session.flush()

            inventory_item.quantity_reserved = Decimal(inventory_item.quantity_reserved) + reserved_quantity
            inventory_item.quantity_total = Decimal(inventory_item.quantity_total)
            db.session.add(inventory_item)

            self._record_history(
                inventory_item=inventory_item,
                service_order=service_order,
                quantity=reserved_quantity,
                operation_type="RESERVATION",
                user_id=user_id,
                company_id=company_id,
                branch_id=branch_id,
            )

        if missing_quantity > Decimal("0"):
            self._record_history(
                inventory_item=inventory_item,
                service_order=service_order,
                quantity=missing_quantity,
                operation_type="AUTO_PURCHASE_REQUEST",
                user_id=user_id,
                company_id=company_id,
                branch_id=branch_id,
            )

        db.session.commit()
        return InventoryReservationResult(
            reservation=reservation,
            reserved_quantity=reserved_quantity,
            missing_quantity=missing_quantity,
            purchase_request=None,
            message=(
                "Część została częściowo zarezerwowana. Brakująca ilość została przekazana do zakupów."
                if missing_quantity > Decimal("0")
                else None
            ),
        )

    def release_reservation(self, *, reservation: InventoryReservation, user_id: int | None, company_id: int, branch_id: int | None) -> None:
        if reservation.status in {InventoryReservationStatusEnum.RELEASED.value, InventoryReservationStatusEnum.CANCELLED.value}:
            return

        reservation.status = InventoryReservationStatusEnum.RELEASED.value
        reservation.released_at = datetime.now(timezone.utc)
        reservation.updated_by = user_id
        reservation.inventory_item.quantity_reserved = max(
            Decimal("0"), Decimal(reservation.inventory_item.quantity_reserved) - Decimal(reservation.quantity)
        )
        db.session.add(reservation)
        db.session.add(reservation.inventory_item)
        self._record_history(
            inventory_item=reservation.inventory_item,
            service_order=reservation.service_order,
            quantity=reservation.quantity,
            operation_type="RESERVATION_RELEASE",
            user_id=user_id,
            company_id=company_id,
            branch_id=branch_id,
        )
        db.session.commit()

    def consume_reservations(self, *, service_order: ServiceOrder, user_id: int | None, company_id: int, branch_id: int | None) -> None:
        reservations = [
            row for row in service_order.inventory_reservations if row.status == InventoryReservationStatusEnum.RESERVED.value
        ]
        for row in reservations:
            row.status = InventoryReservationStatusEnum.CONSUMED.value
            row.updated_by = user_id
            if row.inventory_item.quantity_total >= row.quantity:
                row.inventory_item.quantity_total = Decimal(row.inventory_item.quantity_total) - Decimal(row.quantity)
                row.inventory_item.quantity_reserved = max(Decimal("0"), Decimal(row.inventory_item.quantity_reserved) - Decimal(row.quantity))
            self._record_history(
                inventory_item=row.inventory_item,
                service_order=service_order,
                quantity=row.quantity,
                operation_type="CONSUMPTION",
                user_id=user_id,
                company_id=company_id,
                branch_id=branch_id,
            )
        db.session.commit()

    def _record_history(
        self,
        *,
        inventory_item: InventoryPart,
        service_order: ServiceOrder,
        quantity: Decimal,
        operation_type: str,
        user_id: int | None,
        company_id: int,
        branch_id: int | None,
    ) -> None:
        from app.models.inventory_stock_operation import InventoryStockOperation

        operation = InventoryStockOperation(
            part_id=inventory_item.id,
            user_id=user_id,
            service_order_id=service_order.id,
            operation_type=operation_type,
            quantity=Decimal(quantity),
            stock_before=Decimal(inventory_item.quantity_total) - Decimal(inventory_item.quantity_reserved),
            stock_after=(Decimal(inventory_item.quantity_total) - Decimal(inventory_item.quantity_reserved)),
            document_number=f"SO-{service_order.id}",
            comment=f"Operacja magazynowa: {operation_type}",
            company_id=company_id,
            branch_id=branch_id,
            created_by=user_id,
            updated_by=user_id,
        )
        db.session.add(operation)
