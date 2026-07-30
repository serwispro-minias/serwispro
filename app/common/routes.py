from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Common module</h1>'
        '<p>TODO: implement common routes and views.</p>'
    )
