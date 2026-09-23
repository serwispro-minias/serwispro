from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models.inventory_item import InventoryItem
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
        inventory_item: InventoryItem,
        service_order: ServiceOrder,
        quantity: Decimal,
        user_id: int | None,
        company_id: int,
        branch_id: int | None,
    ) -> InventoryReservationResult:
        quantity = Decimal(quantity)
        if quantity <= Decimal("0"):
            raise ValueError("Ilość rezerwacji musi być większa od zera.")

        reserved = sum(
            (Decimal(row.quantity) for row in inventory_item.inventory_reservations if row.status == InventoryReservationStatusEnum.RESERVED.value),
            Decimal("0"),
        )
        available = Decimal(inventory_item.current_stock) - reserved
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
            reservation = InventoryReservation()
            reservation.inventory_item_id = inventory_item.id
            reservation.service_order_id = service_order.id
            reservation.quantity = reserved_quantity
            reservation.reserved_by = user_id
            reservation.reserved_at = datetime.now(timezone.utc)
            reservation.status = InventoryReservationStatusEnum.RESERVED.value
            reservation.company_id = company_id
            reservation.branch_id = branch_id
            reservation.created_by = user_id
            reservation.updated_by = user_id
            db.session.add(reservation)
            db.session.flush()


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
            if row.inventory_item.current_stock >= row.quantity:
                row.inventory_item.current_stock = int(Decimal(row.inventory_item.current_stock) - Decimal(row.quantity))
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
        inventory_item: InventoryItem,
        service_order: ServiceOrder,
        quantity: Decimal,
        operation_type: str,
        user_id: int | None,
        company_id: int,
        branch_id: int | None,
    ) -> None:
        from app.models.inventory_stock_operation import InventoryStockOperation

        operation = InventoryStockOperation()
        operation.part_id = inventory_item.id
        operation.user_id = user_id
        operation.service_order_id = service_order.id
        operation.operation_type = operation_type
        operation.quantity = Decimal(quantity)
        operation.stock_before = Decimal(inventory_item.current_stock)
        operation.stock_after = Decimal(inventory_item.current_stock)
        operation.document_number = f"SO-{service_order.id}"
        operation.comment = f"Operacja magazynowa: {operation_type}"
        operation.company_id = company_id
        operation.branch_id = branch_id
        operation.created_by = user_id
        operation.updated_by = user_id
        db.session.add(operation)
