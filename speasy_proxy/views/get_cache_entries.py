from pyramid.view import view_config
from pyramid.response import Response
from speasy.core import cache
import logging
from . import pickle_data

log = logging.getLogger(__name__)


@view_config(route_name='get_cache_entries', openapi=True)
def get_cache_entries(request):
    log.debug(f'Client asking for cache entries')
    return Response(content_type="application/python-pickle", body=pickle_data(cache.entries(), request))
