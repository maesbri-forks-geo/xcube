# The MIT License (MIT)
# Copyright (c) 2020 by the xcube development team and contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from typing import Dict

import xarray as xr

from xcube.cli._gen2.genconfig import OutputConfig
from xcube.cli._gen2.storeconfig import get_data_store_instance
from xcube.core.store import DataStore
from xcube.core.store import new_data_writer
from xcube.util.progress import observe_progress


def write_cube(cube: xr.Dataset,
               output_config: OutputConfig,
               store_instances: Dict[str, DataStore] = None) -> str:
    with observe_progress('Writing output', 1) as progress:
        write_params = dict()
        if output_config.store_id:
            writer = get_data_store_instance(output_config.store_id, output_config.store_params, store_instances)
            write_params.update(writer_id=output_config.writer_id, **output_config.write_params)
        else:
            writer = new_data_writer(output_config.writer_id)
            write_params.update(**output_config.store_params, **output_config.write_params)

        # TODO: develop an adapter from Dask callback to ProgressObserver and use it here.
        data_id = writer.write_data(cube,
                                    data_id=output_config.data_id,
                                    replace=output_config.replace or False,
                                    **write_params)
        progress.worked(1)
        return data_id
