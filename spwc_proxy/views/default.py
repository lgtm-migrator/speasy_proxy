from pyramid.view import view_config


@view_config(route_name='home', renderer='../templates/welcome.jinja2')
def my_view(request):
    return {'project': 'spwc-proxy'}