from __future__ import annotations

from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from .exceptions import CatalogNotFoundError, CatalogValidationError
from .forms import (
    AutoIssueMaterialsForm,
    CatalogSearchForm,
    CategoryForm,
    ManufacturerForm,
    MaterialForm,
    MaterialUsageForm,
    PartForm,
    PartReservationForm,
    ServiceItemForm,
    ServiceOrderLineForm,
    StockMovementForm,
    SupplierForm,
)
from .service import CatalogService, default_material_payload, default_part_payload, default_service_payload, tenant_catalog_context


service = CatalogService()


def _tenant() -> tuple[int | None, int | None, int | None]:
    return tenant_catalog_context(current_user)


def _paging() -> tuple[int, str]:
    page = request.args.get("page", 1, type=int)
    query = (request.args.get("q") or "").strip()
    return page, query


def _set_fk_choices(form: PartForm | MaterialForm | ServiceItemForm, company_id: int | None) -> None:
    category_choices = [(0, "---")] + service.category_choices(company_id=company_id)
    supplier_choices = [(0, "---")] + service.supplier_choices(company_id=company_id)
    manufacturer_choices = [(0, "---")] + service.manufacturer_choices(company_id=company_id)

    if hasattr(form, "category_id"):
        form.category_id.choices = category_choices
    if hasattr(form, "supplier_id"):
        form.supplier_id.choices = supplier_choices
    if hasattr(form, "manufacturer_id"):
        form.manufacturer_id.choices = manufacturer_choices


@bp.route("/")
@login_required
def index():
    company_id, _, _ = _tenant()
    categories = service.list_entities(service.categories, page=1, per_page=1, company_id=company_id, query_text=None)
    suppliers = service.list_entities(service.suppliers, page=1, per_page=1, company_id=company_id, query_text=None)
    manufacturers = service.list_entities(service.manufacturers, page=1, per_page=1, company_id=company_id, query_text=None)
    parts = service.list_entities(service.parts, page=1, per_page=1, company_id=company_id, query_text=None)
    materials = service.list_entities(service.materials, page=1, per_page=1, company_id=company_id, query_text=None)
    services_data = service.list_entities(service.services, page=1, per_page=1, company_id=company_id, query_text=None)

    return render_template(
        "catalog/index.html",
        counts={
            "categories": categories["total"],
            "suppliers": suppliers["total"],
            "manufacturers": manufacturers["total"],
            "parts": parts["total"],
            "materials": materials["total"],
            "services": services_data["total"],
        },
    )


@bp.route("/categories")
@login_required
def categories_index():
    page, query = _paging()
    company_id, _, _ = _tenant()
    search_form = CatalogSearchForm(request.args, meta={"csrf": False})
    data = service.list_entities(service.categories, page=page, per_page=20, company_id=company_id, query_text=query)
    return render_template("catalog/categories_index.html", categories=data, q=query, search_form=search_form)


@bp.route("/categories/create", methods=["GET", "POST"])
@login_required
def categories_create():
    company_id, branch_id, _ = _tenant()
    form = CategoryForm()

    if form.validate_on_submit():
        try:
            entity = service.create_entity(service.categories, form.data, company_id=company_id, branch_id=branch_id)
            flash("Kategoria została utworzona.", "success")
            return redirect(url_for("catalog.categories_details", category_id=entity.id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/categories_form.html", form=form, title="Nowa kategoria", entity=None)


@bp.route("/categories/<int:category_id>")
@login_required
def categories_details(category_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.categories, category_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)
    return render_template("catalog/categories_details.html", entity=entity)


@bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@login_required
def categories_edit(category_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.categories, category_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)

    form = CategoryForm(obj=entity)
    if form.validate_on_submit():
        try:
            service.update_entity(service.categories, category_id, form.data, company_id=company_id)
            flash("Kategoria została zaktualizowana.", "success")
            return redirect(url_for("catalog.categories_details", category_id=category_id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/categories_form.html", form=form, title="Edycja kategorii", entity=entity)


@bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def categories_delete(category_id: int):
    company_id, _, _ = _tenant()
    try:
        service.delete_entity(service.categories, category_id, company_id=company_id)
        flash("Kategoria została usunięta.", "success")
    except CatalogNotFoundError:
        flash("Nie znaleziono kategorii.", "danger")
    return redirect(url_for("catalog.categories_index"))


@bp.route("/suppliers")
@login_required
def suppliers_index():
    page, query = _paging()
    company_id, _, _ = _tenant()
    search_form = CatalogSearchForm(request.args, meta={"csrf": False})
    data = service.list_entities(service.suppliers, page=page, per_page=20, company_id=company_id, query_text=query)
    return render_template("catalog/suppliers_index.html", suppliers=data, q=query, search_form=search_form)


@bp.route("/suppliers/create", methods=["GET", "POST"])
@login_required
def suppliers_create():
    company_id, branch_id, _ = _tenant()
    form = SupplierForm()

    if form.validate_on_submit():
        try:
            entity = service.create_entity(service.suppliers, form.data, company_id=company_id, branch_id=branch_id)
            flash("Dostawca został utworzony.", "success")
            return redirect(url_for("catalog.suppliers_details", supplier_id=entity.id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/suppliers_form.html", form=form, title="Nowy dostawca", entity=None)


@bp.route("/suppliers/<int:supplier_id>")
@login_required
def suppliers_details(supplier_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.suppliers, supplier_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)
    return render_template("catalog/suppliers_details.html", entity=entity)


@bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
def suppliers_edit(supplier_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.suppliers, supplier_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)

    form = SupplierForm(obj=entity)
    if form.validate_on_submit():
        try:
            service.update_entity(service.suppliers, supplier_id, form.data, company_id=company_id)
            flash("Dostawca został zaktualizowany.", "success")
            return redirect(url_for("catalog.suppliers_details", supplier_id=supplier_id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/suppliers_form.html", form=form, title="Edycja dostawcy", entity=entity)


@bp.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
@login_required
def suppliers_delete(supplier_id: int):
    company_id, _, _ = _tenant()
    try:
        service.delete_entity(service.suppliers, supplier_id, company_id=company_id)
        flash("Dostawca został usunięty.", "success")
    except CatalogNotFoundError:
        flash("Nie znaleziono dostawcy.", "danger")
    return redirect(url_for("catalog.suppliers_index"))


@bp.route("/manufacturers")
@login_required
def manufacturers_index():
    page, query = _paging()
    company_id, _, _ = _tenant()
    search_form = CatalogSearchForm(request.args, meta={"csrf": False})
    data = service.list_entities(service.manufacturers, page=page, per_page=20, company_id=company_id, query_text=query)
    return render_template("catalog/manufacturers_index.html", manufacturers=data, q=query, search_form=search_form)


@bp.route("/manufacturers/create", methods=["GET", "POST"])
@login_required
def manufacturers_create():
    company_id, branch_id, _ = _tenant()
    form = ManufacturerForm()

    if form.validate_on_submit():
        try:
            entity = service.create_entity(service.manufacturers, form.data, company_id=company_id, branch_id=branch_id)
            flash("Producent został utworzony.", "success")
            return redirect(url_for("catalog.manufacturers_details", manufacturer_id=entity.id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/manufacturers_form.html", form=form, title="Nowy producent", entity=None)


@bp.route("/manufacturers/<int:manufacturer_id>")
@login_required
def manufacturers_details(manufacturer_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.manufacturers, manufacturer_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)
    return render_template("catalog/manufacturers_details.html", entity=entity)


@bp.route("/manufacturers/<int:manufacturer_id>/edit", methods=["GET", "POST"])
@login_required
def manufacturers_edit(manufacturer_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.manufacturers, manufacturer_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)

    form = ManufacturerForm(obj=entity)
    if form.validate_on_submit():
        try:
            service.update_entity(service.manufacturers, manufacturer_id, form.data, company_id=company_id)
            flash("Producent został zaktualizowany.", "success")
            return redirect(url_for("catalog.manufacturers_details", manufacturer_id=manufacturer_id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/manufacturers_form.html", form=form, title="Edycja producenta", entity=entity)


@bp.route("/manufacturers/<int:manufacturer_id>/delete", methods=["POST"])
@login_required
def manufacturers_delete(manufacturer_id: int):
    company_id, _, _ = _tenant()
    try:
        service.delete_entity(service.manufacturers, manufacturer_id, company_id=company_id)
        flash("Producent został usunięty.", "success")
    except CatalogNotFoundError:
        flash("Nie znaleziono producenta.", "danger")
    return redirect(url_for("catalog.manufacturers_index"))


@bp.route("/parts")
@login_required
def parts_index():
    page, query = _paging()
    company_id, _, _ = _tenant()
    search_form = CatalogSearchForm(request.args, meta={"csrf": False})
    data = service.list_entities(service.parts, page=page, per_page=20, company_id=company_id, query_text=query)
    return render_template("catalog/parts_index.html", parts=data, q=query, search_form=search_form)


@bp.route("/parts/create", methods=["GET", "POST"])
@login_required
def parts_create():
    company_id, branch_id, _ = _tenant()
    form = PartForm()
    _set_fk_choices(form, company_id)

    if request.method == "GET":
        defaults = default_part_payload()
        form.unit.data = defaults["unit"]
        form.current_stock.data = defaults["current_stock"]
        form.minimum_stock.data = defaults["minimum_stock"]
        form.purchase_price_net.data = defaults["purchase_price_net"]
        form.sale_price_net.data = defaults["sale_price_net"]
        form.vat_rate.data = defaults["vat_rate"]
        form.is_sellable.data = defaults["is_sellable"]
        form.is_reservable.data = defaults["is_reservable"]

    if form.validate_on_submit():
        try:
            entity = service.create_entity(service.parts, form.data, company_id=company_id, branch_id=branch_id)
            flash("Część została utworzona.", "success")
            return redirect(url_for("catalog.parts_details", part_id=entity.id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/parts_form.html", form=form, title="Nowa część", entity=None)


@bp.route("/parts/<int:part_id>")
@login_required
def parts_details(part_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.parts, part_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)

    movement_form = StockMovementForm()
    return render_template("catalog/parts_details.html", entity=entity, movement_form=movement_form)


@bp.route("/parts/<int:part_id>/edit", methods=["GET", "POST"])
@login_required
def parts_edit(part_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.parts, part_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)

    form = PartForm(obj=entity)
    _set_fk_choices(form, company_id)
    if request.method == "GET":
        form.current_stock.data = Decimal(entity.current_stock)
        form.minimum_stock.data = Decimal(entity.minimum_stock)
        form.purchase_price_net.data = Decimal(entity.purchase_price_net)
        form.sale_price_net.data = Decimal(entity.sale_price_net)
        form.vat_rate.data = Decimal(entity.vat_rate)

    if form.validate_on_submit():
        try:
            service.update_entity(service.parts, part_id, form.data, company_id=company_id)
            flash("Część została zaktualizowana.", "success")
            return redirect(url_for("catalog.parts_details", part_id=part_id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/parts_form.html", form=form, title="Edycja części", entity=entity)


@bp.route("/parts/<int:part_id>/delete", methods=["POST"])
@login_required
def parts_delete(part_id: int):
    company_id, _, _ = _tenant()
    try:
        service.delete_entity(service.parts, part_id, company_id=company_id)
        flash("Część została usunięta.", "success")
    except CatalogNotFoundError:
        flash("Nie znaleziono części.", "danger")
    return redirect(url_for("catalog.parts_index"))


@bp.route("/parts/<int:part_id>/movements", methods=["POST"])
@login_required
def parts_add_movement(part_id: int):
    company_id, branch_id, user_id = _tenant()
    form = StockMovementForm()
    if not form.validate_on_submit():
        flash("Nie udało się zapisać ruchu magazynowego.", "danger")
        return redirect(url_for("catalog.parts_details", part_id=part_id))

    try:
        service.add_stock_movement(
            entity_type="part",
            entity_id=part_id,
            movement_type=form.movement_type.data,
            quantity=Decimal(form.quantity.data),
            reference_type=form.reference_type.data,
            reference_id=form.reference_id.data,
            note=form.note.data,
            user_id=user_id,
            company_id=company_id,
            branch_id=branch_id,
        )
        flash("Ruch magazynowy został zapisany.", "success")
    except (CatalogValidationError, CatalogNotFoundError) as exc:
        flash(str(exc), "danger")

    return redirect(url_for("catalog.parts_details", part_id=part_id))


@bp.route("/materials")
@login_required
def materials_index():
    page, query = _paging()
    company_id, _, _ = _tenant()
    search_form = CatalogSearchForm(request.args, meta={"csrf": False})
    data = service.list_entities(service.materials, page=page, per_page=20, company_id=company_id, query_text=query)
    return render_template("catalog/materials_index.html", materials=data, q=query, search_form=search_form)


@bp.route("/materials/create", methods=["GET", "POST"])
@login_required
def materials_create():
    company_id, branch_id, _ = _tenant()
    form = MaterialForm()
    _set_fk_choices(form, company_id)

    if request.method == "GET":
        defaults = default_material_payload()
        form.unit.data = defaults["unit"]
        form.current_stock.data = defaults["current_stock"]
        form.minimum_stock.data = defaults["minimum_stock"]
        form.purchase_price_net.data = defaults["purchase_price_net"]
        form.default_usage_qty.data = defaults["default_usage_qty"]
        form.vat_rate.data = defaults["vat_rate"]
        form.auto_issue_on_order.data = defaults["auto_issue_on_order"]

    if form.validate_on_submit():
        try:
            entity = service.create_entity(service.materials, form.data, company_id=company_id, branch_id=branch_id)
            flash("Materiał został utworzony.", "success")
            return redirect(url_for("catalog.materials_details", material_id=entity.id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/materials_form.html", form=form, title="Nowy materiał", entity=None)


@bp.route("/materials/<int:material_id>")
@login_required
def materials_details(material_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.materials, material_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)

    movement_form = StockMovementForm()
    return render_template("catalog/materials_details.html", entity=entity, movement_form=movement_form)


@bp.route("/materials/<int:material_id>/edit", methods=["GET", "POST"])
@login_required
def materials_edit(material_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.materials, material_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)

    form = MaterialForm(obj=entity)
    _set_fk_choices(form, company_id)
    if request.method == "GET":
        form.current_stock.data = Decimal(entity.current_stock)
        form.minimum_stock.data = Decimal(entity.minimum_stock)
        form.purchase_price_net.data = Decimal(entity.purchase_price_net)
        form.default_usage_qty.data = Decimal(entity.default_usage_qty)
        form.vat_rate.data = Decimal(entity.vat_rate)

    if form.validate_on_submit():
        try:
            service.update_entity(service.materials, material_id, form.data, company_id=company_id)
            flash("Materiał został zaktualizowany.", "success")
            return redirect(url_for("catalog.materials_details", material_id=material_id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/materials_form.html", form=form, title="Edycja materiału", entity=entity)


@bp.route("/materials/<int:material_id>/delete", methods=["POST"])
@login_required
def materials_delete(material_id: int):
    company_id, _, _ = _tenant()
    try:
        service.delete_entity(service.materials, material_id, company_id=company_id)
        flash("Materiał został usunięty.", "success")
    except CatalogNotFoundError:
        flash("Nie znaleziono materiału.", "danger")
    return redirect(url_for("catalog.materials_index"))


@bp.route("/materials/<int:material_id>/movements", methods=["POST"])
@login_required
def materials_add_movement(material_id: int):
    company_id, branch_id, user_id = _tenant()
    form = StockMovementForm()
    if not form.validate_on_submit():
        flash("Nie udało się zapisać ruchu magazynowego.", "danger")
        return redirect(url_for("catalog.materials_details", material_id=material_id))

    try:
        service.add_stock_movement(
            entity_type="material",
            entity_id=material_id,
            movement_type=form.movement_type.data,
            quantity=Decimal(form.quantity.data),
            reference_type=form.reference_type.data,
            reference_id=form.reference_id.data,
            note=form.note.data,
            user_id=user_id,
            company_id=company_id,
            branch_id=branch_id,
        )
        flash("Ruch magazynowy został zapisany.", "success")
    except (CatalogValidationError, CatalogNotFoundError) as exc:
        flash(str(exc), "danger")

    return redirect(url_for("catalog.materials_details", material_id=material_id))


@bp.route("/services")
@login_required
def services_index():
    page, query = _paging()
    company_id, _, _ = _tenant()
    search_form = CatalogSearchForm(request.args, meta={"csrf": False})
    data = service.list_entities(service.services, page=page, per_page=20, company_id=company_id, query_text=query)
    return render_template("catalog/services_index.html", services_data=data, q=query, search_form=search_form)


@bp.route("/services/create", methods=["GET", "POST"])
@login_required
def services_create():
    company_id, branch_id, _ = _tenant()
    form = ServiceItemForm()
    _set_fk_choices(form, company_id)

    if request.method == "GET":
        defaults = default_service_payload()
        form.default_price_net.data = defaults["default_price_net"]
        form.vat_rate.data = defaults["vat_rate"]
        form.standard_duration_minutes.data = defaults["standard_duration_minutes"]
        form.is_sellable.data = defaults["is_sellable"]

    if form.validate_on_submit():
        try:
            entity = service.create_entity(service.services, form.data, company_id=company_id, branch_id=branch_id)
            flash("Usługa została utworzona.", "success")
            return redirect(url_for("catalog.services_details", service_id=entity.id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/services_form.html", form=form, title="Nowa usługa", entity=None)


@bp.route("/services/<int:service_id>")
@login_required
def services_details(service_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.services, service_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)
    return render_template("catalog/services_details.html", entity=entity)


@bp.route("/services/<int:service_id>/edit", methods=["GET", "POST"])
@login_required
def services_edit(service_id: int):
    company_id, _, _ = _tenant()
    try:
        entity = service.get_entity_or_404(service.services, service_id, company_id=company_id)
    except CatalogNotFoundError:
        abort(404)

    form = ServiceItemForm(obj=entity)
    _set_fk_choices(form, company_id)
    if request.method == "GET":
        form.default_price_net.data = Decimal(entity.default_price_net)
        form.vat_rate.data = Decimal(entity.vat_rate)

    if form.validate_on_submit():
        try:
            service.update_entity(service.services, service_id, form.data, company_id=company_id)
            flash("Usługa została zaktualizowana.", "success")
            return redirect(url_for("catalog.services_details", service_id=service_id))
        except CatalogValidationError as exc:
            flash(str(exc), "danger")

    return render_template("catalog/services_form.html", form=form, title="Edycja usługi", entity=entity)


@bp.route("/services/<int:service_id>/delete", methods=["POST"])
@login_required
def services_delete(service_id: int):
    company_id, _, _ = _tenant()
    try:
        service.delete_entity(service.services, service_id, company_id=company_id)
        flash("Usługa została usunięta.", "success")
    except CatalogNotFoundError:
        flash("Nie znaleziono usługi.", "danger")
    return redirect(url_for("catalog.services_index"))


@bp.route("/orders/<int:order_id>", methods=["GET"])
@login_required
def order_catalog(order_id: int):
    company_id, branch_id, _ = _tenant()

    try:
        summary = service.get_order_catalog_summary(order_id=order_id, company_id=company_id, branch_id=branch_id)
    except CatalogNotFoundError:
        abort(404)

    reservation_form = PartReservationForm()
    reservation_form.part_id.choices = service.part_choices(company_id=company_id)

    usage_form = MaterialUsageForm()
    usage_form.material_id.choices = service.material_choices(company_id=company_id)

    service_line_form = ServiceOrderLineForm()
    service_line_form.service_item_id.choices = service.service_choices(company_id=company_id)

    auto_issue_form = AutoIssueMaterialsForm()

    return render_template(
        "catalog/order_catalog.html",
        summary=summary,
        reservation_form=reservation_form,
        usage_form=usage_form,
        service_line_form=service_line_form,
        auto_issue_form=auto_issue_form,
    )


@bp.route("/orders/<int:order_id>/reserve-part", methods=["POST"])
@login_required
def order_reserve_part(order_id: int):
    company_id, branch_id, user_id = _tenant()
    form = PartReservationForm()
    form.part_id.choices = service.part_choices(company_id=company_id)

    if not form.validate_on_submit():
        flash("Nie udało się zapisać rezerwacji części.", "danger")
        return redirect(url_for("catalog.order_catalog", order_id=order_id))

    try:
        result = service.reserve_part_for_order(
            order_id=order_id,
            part_id=form.part_id.data,
            quantity=Decimal(form.quantity.data),
            user_id=user_id,
            company_id=company_id,
            branch_id=branch_id,
        )
        if result.demand_created:
            flash(
                f"Brak stanu magazynowego. Utworzono zapotrzebowanie #{result.demand_id} na brakującą ilość {result.demand_missing_quantity}.",
                "warning",
            )
        else:
            flash("Rezerwacja części została zapisana.", "success")
    except (CatalogNotFoundError, CatalogValidationError) as exc:
        flash(str(exc), "danger")

    return redirect(url_for("catalog.order_catalog", order_id=order_id))


@bp.route("/orders/<int:order_id>/issue-material", methods=["POST"])
@login_required
def order_issue_material(order_id: int):
    company_id, branch_id, user_id = _tenant()
    form = MaterialUsageForm()
    form.material_id.choices = service.material_choices(company_id=company_id)

    if not form.validate_on_submit():
        flash("Nie udało się zapisać zużycia materiału.", "danger")
        return redirect(url_for("catalog.order_catalog", order_id=order_id))

    try:
        service.issue_material_to_order(
            order_id=order_id,
            material_id=form.material_id.data,
            quantity=Decimal(form.quantity.data),
            user_id=user_id,
            company_id=company_id,
            branch_id=branch_id,
        )
        flash("Zużycie materiału zostało zapisane.", "success")
    except (CatalogNotFoundError, CatalogValidationError) as exc:
        flash(str(exc), "danger")

    return redirect(url_for("catalog.order_catalog", order_id=order_id))


@bp.route("/orders/<int:order_id>/add-service-line", methods=["POST"])
@login_required
def order_add_service_line(order_id: int):
    company_id, branch_id, _ = _tenant()
    form = ServiceOrderLineForm()
    form.service_item_id.choices = service.service_choices(company_id=company_id)

    if not form.validate_on_submit():
        flash("Nie udało się dodać usługi do zlecenia.", "danger")
        return redirect(url_for("catalog.order_catalog", order_id=order_id))

    try:
        service.add_service_line_to_order(
            order_id=order_id,
            service_item_id=form.service_item_id.data,
            quantity=Decimal(form.quantity.data),
            company_id=company_id,
            branch_id=branch_id,
        )
        flash("Usługa została dodana do zlecenia.", "success")
    except (CatalogNotFoundError, CatalogValidationError) as exc:
        flash(str(exc), "danger")

    return redirect(url_for("catalog.order_catalog", order_id=order_id))


@bp.route("/orders/<int:order_id>/auto-issue-materials", methods=["POST"])
@login_required
def order_auto_issue_materials(order_id: int):
    company_id, branch_id, user_id = _tenant()
    form = AutoIssueMaterialsForm()
    if not form.validate_on_submit():
        flash("Nie udało się uruchomić automatycznego odpisania.", "danger")
        return redirect(url_for("catalog.order_catalog", order_id=order_id))

    try:
        usages = service.apply_auto_issue_materials(
            order_id=order_id,
            user_id=user_id,
            company_id=company_id,
            branch_id=branch_id,
        )
        if usages:
            flash(f"Automatycznie odpisano {len(usages)} materiał(ów).", "success")
        else:
            flash("Brak materiałów do automatycznego odpisania.", "warning")
    except (CatalogNotFoundError, CatalogValidationError) as exc:
        flash(str(exc), "danger")

    return redirect(url_for("catalog.order_catalog", order_id=order_id))
