from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import bp
from .exceptions import CustomerAlreadyExistsError, CustomerNotFoundError, CustomerValidationError
from .forms import CustomerForm
from .repository import CustomerRepository
from .services import CustomerService

service = CustomerService(CustomerRepository())


@bp.route('/', methods=['GET'])
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    query = request.args.get('q', '', type=str)
    per_page = 20

    if query:
        customers = service.search_customers(
            query=query,
            page=page,
            per_page=per_page,
            company_id=current_user.company_id,
        )
    else:
        customers = service.list_customers(
            page=page,
            per_page=per_page,
            company_id=current_user.company_id,
        )

    return render_template(
        'customers/index.html',
        customers=customers,
        q=query,
    )


@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    form = CustomerForm()
    if form.validate_on_submit():
        try:
            customer = service.create_customer(form.data, company_id=current_user.company_id)
            flash('Klient został utworzony.', 'success')
            return redirect(url_for('customers.details', customer_id=customer.id))
        except (CustomerValidationError, CustomerAlreadyExistsError) as exc:
            flash(str(exc), 'danger')

    return render_template('customers/form.html', form=form, title='Dodaj klienta', customer=None)


@bp.route('/<int:customer_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(customer_id: int):
    customer = service.get_customer(customer_id, company_id=current_user.company_id)
    if customer is None:
        flash('Nie znaleziono klienta.', 'danger')
        return redirect(url_for('customers.index'))

    form = CustomerForm(obj=customer)
    if form.validate_on_submit():
        try:
            service.update_customer(customer_id, form.data, company_id=current_user.company_id)
            flash('Dane klienta zostały zaktualizowane.', 'success')
            return redirect(url_for('customers.details', customer_id=customer.id))
        except (CustomerValidationError, CustomerAlreadyExistsError) as exc:
            flash(str(exc), 'danger')

    return render_template(
        'customers/form.html',
        form=form,
        title='Edytuj klienta',
        customer=customer,
    )


@bp.route('/<int:customer_id>')
@login_required
def details(customer_id: int):
    customer = service.get_customer(customer_id, company_id=current_user.company_id)
    if customer is None:
        flash('Nie znaleziono klienta.', 'danger')
        return redirect(url_for('customers.index'))

    return render_template('customers/details.html', customer=customer)


@bp.route('/<int:customer_id>/delete', methods=['POST'])
@login_required
def delete(customer_id: int):
    try:
        service.delete_customer(customer_id, company_id=current_user.company_id)
        flash('Klient został usunięty.', 'success')
    except CustomerNotFoundError:
        flash('Nie znaleziono klienta.', 'danger')

    return redirect(url_for('customers.index'))
