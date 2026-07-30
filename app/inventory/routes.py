from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Inventory module</h1>'
        '<p>TODO: implement inventory routes and views.</p>'
    )
