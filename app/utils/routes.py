from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Utils module</h1>'
        '<p>TODO: implement utils routes and views.</p>'
    )
