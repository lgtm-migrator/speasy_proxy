import time

from pyramid.view import view_config
from pyramid.response import Response
import speasy as spz
from speasy.products.variable import SpeasyVariable
from datetime import datetime
from speasy.products.variable import to_dictionary
from ..inventory_updater import EnsureUpdatedInventory
from ..bokeh_backend import plot_data
import zstd
import logging
import uuid
import json
from astropy.units.quantity import Quantity
import numpy as np

from . import pickle_data

log = logging.getLogger(__name__)

MAX_BOKEH_DATA_LENGTH = 1000000


def dt_to_str(dt: datetime):
    return dt.isoformat()


def ts_to_str(ts: float):
    return dt_to_str(datetime.utcfromtimestamp(ts))


def _values_as_array(values):
    if type(values) is Quantity:
        return values.view(np.ndarray)
    return values


def to_json(var: SpeasyVariable) -> str:
    var.replace_fillval_by_nan(inplace=True)
    return json.dumps(var.to_dictionary(array_to_list=True))


@view_config(route_name='get_data', openapi=True, decorator=(EnsureUpdatedInventory(),))
def get_data(request):
    request_start_time = time.time_ns()
    request_id = uuid.uuid4()
    extra_params = {}
    product = request.params.get("path", None)
    start_time = request.params.get("start_time", None)
    stop_time = request.params.get("stop_time", None)
    if 'X-Real-IP' in request.headers:
        extra_http_headers = {'X-Forwarded-For': request.headers['X-Real-IP']}
        client_chain = request.headers['X-Real-IP']
    else:
        client_chain = request.client_addr
        extra_http_headers = None
    for value, name in ((product, "path"), (start_time, "start_time"), (stop_time, "stop_time")):
        if value is None:
            log.error(f'Missing parameter: {name}')
            return Response(
                content_type="text/plain",
                body=f"Error: missing {name} parameter"
            )
    for parameter in ("coordinate_system",):
        if parameter in request.params:
            extra_params[parameter] = request.params[parameter]

    log.debug(f'New request {request_id}: {product} {start_time} {stop_time} from {client_chain}')

    var = spz.get_data(product=product, start_time=start_time, stop_time=stop_time,
                       extra_http_headers=extra_http_headers, **extra_params)

    result, mime = compress_if_asked(*encode_output(var, request), request)

    request_duration = (time.time_ns() - request_start_time) / 1000000.

    if var is not None:
        if len(var.time):
            log.debug(
                f'{request_id}, duration = {request_duration}ms, Got data: data shape = {var.values.shape}, data start time = {var.time[0]}, data stop time = {var.time[-1]}')
        else:
            log.debug(f'{request_id}, duration = {request_duration}ms, Got empty data')
    else:
        log.debug(f'{request_id}, duration = {request_duration}ms, Got None')

    del var

    return Response(content_type=mime, body=result,
                    headerlist=[('Access-Control-Allow-Origin', '*'), ('Content-Type', mime)])


def encode_output(var, request):
    data = None
    if var is not None:
        output_format = request.params.get("format", "python_dict")
        if output_format == "python_dict":
            data = to_dictionary(var)
        elif output_format == 'speasy_variable':
            data = var
        elif output_format == 'html_bokeh':
            if len(var) < MAX_BOKEH_DATA_LENGTH:
                return plot_data(product=request.params.get("path", ""), data=var,
                                 start_time=request.params.get("start_time"), stop_time=request.params.get("stop_time"),
                                 request=request), 'text/html; charset=UTF-8'
            else:
                return plot_data(product=request.params.get("path", ""), data=var[:MAX_BOKEH_DATA_LENGTH],
                                 start_time=request.params.get("start_time"), stop_time=request.params.get("stop_time"),
                                 request=request), 'text/html; charset=UTF-8'
        elif output_format == 'json':
            if len(var) < MAX_BOKEH_DATA_LENGTH:
                return to_json(var), 'application/json; charset=UTF-8'
            else:
                return to_json(var[:MAX_BOKEH_DATA_LENGTH]), 'application/json; charset=UTF-8'

    return pickle_data(data, request), "application/python-pickle"


def compress_if_asked(data, mime, request):
    if request.params.get("zstd_compression", "false") == "true":
        mime = "application/x-zstd-compressed"
        data = zstd.compress(data)
    return data, mime
