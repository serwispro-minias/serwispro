from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Dashboard module</h1>'
        '<p>TODO: implement dashboard routes and views.</p>'
    )
