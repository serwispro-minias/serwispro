from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Devices module</h1>'
        '<p>TODO: implement devices routes and views.</p>'
    )
