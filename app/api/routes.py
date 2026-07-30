from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Api module</h1>'
        '<p>TODO: implement api routes and views.</p>'
    )
