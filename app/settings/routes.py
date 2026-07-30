from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Settings module</h1>'
        '<p>TODO: implement settings routes and views.</p>'
    )
