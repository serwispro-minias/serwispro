from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Reports module</h1>'
        '<p>TODO: implement reports routes and views.</p>'
    )
