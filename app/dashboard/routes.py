from __future__ import annotations

from flask import render_template
from flask_login import login_required

from . import bp
from .service import DashboardService

dashboard_service = DashboardService()


@bp.route("/")
@login_required
def index():
    """Render dashboard start panel using data from DashboardService."""

    dashboard_data = dashboard_service.get_dashboard_data()
    return render_template(
        "dashboard/index.html",
        stats=dashboard_data.stats,
        recent_customers=dashboard_data.recent_customers,
        recent_repairs=dashboard_data.recent_repairs,
        repairs_module_available=dashboard_data.repairs_module_available,
    )