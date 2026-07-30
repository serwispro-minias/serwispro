from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Services module</h1>'
        '<p>TODO: implement services routes and views.</p>'
    )
