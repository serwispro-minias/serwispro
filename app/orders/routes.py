from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Orders module</h1>'
        '<p>TODO: implement orders routes and views.</p>'
    )
