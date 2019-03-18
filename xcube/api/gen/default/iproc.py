# The MIT License (MIT)
# Copyright (c) 2019 by the xcube development team and contributors
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

from typing import Tuple, Optional
import numpy as np

import xarray as xr

from xcube.util.constants import CRS_WKT_EPSG_4326
from xcube.util.timecoord import get_time_in_days_since_1970
from ..iproc import XYInputProcessor, register_input_processor, ReprojectionInfo


class DefaultInputProcessor(XYInputProcessor):
    """
    Default input processor that expects input datasets to have the xcube standard format:

    * Have dimensions ``lat``, ``lon``, optionally ``time`` of length 1;
    * have coordinate variables ``lat[lat]``, ``lon[lat]``, ``time[time]`` (opt.), ``time_bnds[time, 2]`` (opt.);
    * have coordinate variables ``lat[lat]``, ``lon[lat]`` as decimal degrees on WGS84 ellipsoid,
      both linearly increasing with same constant delta;
    * have coordinate variable ``time[time]`` representing a date+time values with defined CF "units" attribute;
    * have any data variables of form ``<var>[time, lat, lon]``;
    * have global attribute pairs (``time_coverage_start``, ``time_coverage_end``), or (``start_time``, ``stop_time``)
      if ``time`` coordinate is missing.

    The default input processor can be configured by the following parameters:

    * ``input_reader`` the input reader identifier, default is "netcdf4".

    """

    def __init__(self):
        self._input_reader = 'netcdf4'

    @property
    def name(self) -> str:
        return 'default'

    @property
    def description(self) -> str:
        return 'Single-scene NetCDF/CF inputs in xcube standard format'

    def configure(self, input_reader: str = 'netcdf4'):
        self._input_reader = input_reader

    @property
    def input_reader(self) -> str:
        return self._input_reader

    def pre_process(self, dataset: xr.Dataset) -> xr.Dataset:
        self._validate(dataset)
        if "time" in dataset:
            return dataset.squeeze("time")
        return dataset

    def get_reprojection_info(self, dataset: xr.Dataset) -> ReprojectionInfo:
        return ReprojectionInfo(xy_var_names=('lon', 'lat'),
                                xy_crs=CRS_WKT_EPSG_4326,
                                xy_gcp_step=(max(1, len(dataset.lon) // 4),
                                             max(1, len(dataset.lat) // 4)))

    def get_time_range(self, dataset: xr.Dataset) -> Tuple[float, float]:
        time_coverage_start, time_coverage_end = None, None
        if "time" in dataset:
            time = dataset["time"]
            time_bnds_name = time.attrs.get("bounds", "time_bnds")
            if time_bnds_name in dataset:
                time_bnds = dataset[time_bnds_name]
                if time_bnds.shape == (1, 2):
                    time_coverage_start = str(time_bnds[0][0].data)
                    time_coverage_end = str(time_bnds[0][1].data)
            if time_coverage_start is None or time_coverage_end is None:
                time_coverage_start, time_coverage_end = self.get_time_range_from_attrs(dataset)
            if time_coverage_start is None or time_coverage_end is None:
                if time.shape == (1,):
                    time_coverage_start = str(time[0].data)
                    time_coverage_end = time_coverage_start
        if time_coverage_start is None or time_coverage_end is None:
            time_coverage_start, time_coverage_end = self.get_time_range_from_attrs(dataset)
        if time_coverage_start is None or time_coverage_end is None:
            raise ValueError("invalid input: missing time coverage information in dataset")

        return get_time_in_days_since_1970(time_coverage_start), get_time_in_days_since_1970(time_coverage_end)

    @classmethod
    def get_time_range_from_attrs(cls, dataset: xr.Dataset) -> Tuple[str, str]:
        time_start = time_stop = None
        if "time_coverage_start" in dataset.attrs:
            time_start = str(dataset.attrs["time_coverage_start"])
            time_stop = str(dataset.attrs.get("time_coverage_end", time_start))
        elif "time_start" in dataset.attrs:
            time_start = str(dataset.attrs["time_start"])
            time_stop = str(dataset.attrs.get("time_stop", dataset.attrs.get("time_end", time_start)))
        elif "start_time" in dataset.attrs:
            time_start = str(dataset.attrs["start_time"])
            time_stop = str(dataset.attrs.get("stop_time", dataset.attrs.get("end_time", time_start)))
        return time_start, time_stop



    def _validate(self, dataset):
        self._check_coordinate_var(dataset, "lon", min_length=2)
        self._check_coordinate_var(dataset, "lat", min_length=2)
        if "time" in dataset.dims:
            self._check_coordinate_var(dataset, "time", max_length=1)
            required_dims = ("time", "lat", "lon")
        else:
            required_dims = ("lat", "lon")
        count = 0
        for var_name in dataset.data_vars:
            var = dataset.data_vars[var_name]
            if var.dims == required_dims:
                count += 1
        if count == 0:
            raise ValueError(f"dataset has no variables with required dimensions {required_dims!r}")

    # noinspection PyMethodMayBeStatic
    def _check_coordinate_var(self, dataset: xr.Dataset, coord_var_name: str,
                              min_length: int = None, max_length: int = None):
        if coord_var_name not in dataset.coords:
            raise ValueError(f'missing coordinate variable "{coord_var_name}"')
        coord_var = dataset.coords[coord_var_name]
        if len(coord_var.shape) != 1:
            raise ValueError('coordinate variable "lon" must be 1D')
        coord_var_bnds_name = coord_var.attrs.get("bounds", coord_var_name + "_bnds")
        if coord_var_bnds_name in dataset:
            coord_bnds_var = dataset[coord_var_bnds_name]
            expected_shape = (len(coord_var), 2)
            if coord_bnds_var.shape != expected_shape:
                raise ValueError(f'coordinate bounds variable "{coord_bnds_var}" must have shape {expected_shape!r}')
        else:
            if min_length is not None and len(coord_var) < min_length:
                raise ValueError(f'coordinate variable "{coord_var_name}" must have at least {min_length} value(s)')
            if max_length is not None and len(coord_var) > max_length:
                raise ValueError(f'coordinate variable "{coord_var_name}" must have no more than {max_length} value(s)')

def _normalize_lon_360(dataset: xr.Dataset) -> xr.Dataset:
    """
    Fix the longitude of the given dataset ``ds`` so that it ranges from -180 to +180 degrees.

    :param dataset: The dataset whose longitudes may be given in the range 0 to 360.
    :return: The fixed dataset or the original dataset.
    """

    if 'lon' not in dataset.coords:
        return dataset

    lon_var = dataset.coords['lon']

    if len(lon_var.shape) != 1:
        return dataset

    lon_size = lon_var.shape[0]
    if lon_size < 2:
        return dataset

    lon_size_05 = lon_size // 2
    lon_values = lon_var.values
    if not np.any(lon_values[lon_size_05:] > 180.):
        return dataset


    dataset = dataset.roll(lon=lon_size_05)
    dataset = dataset.assign_coords(lon=(((dataset.lon + 180) % 360) - 180))
    dataset = adjust_spatial_attrs_impl(dataset, True)

    return dataset

def adjust_spatial_attrs_impl(dataset: xr.Dataset, allow_point: bool) -> xr.Dataset:
    """
    Adjust the global spatial attributes of the dataset by doing some
    introspection of the dataset and adjusting the appropriate attributes
    accordingly.

    In case the determined attributes do not exist in the dataset, these will
    be added.

    For more information on suggested global attributes see
    `Attribute Convention for Data Discovery
    <http://wiki.esipfed.org/index.php/Attribute_Convention_for_Data_Discovery>`_

    :param dataset: Dataset to adjust
    :param allow_point: Whether to accept single point cells
    :return: Adjusted dataset
    """

    copied = False

    for dim in ('lon', 'lat'):
        geo_spatial_attrs = _get_geo_spatial_cf_attrs_from_var(dataset, dim, allow_point=allow_point)
        if geo_spatial_attrs:
            # Copy any new attributes into the shallow Dataset copy
            for key in geo_spatial_attrs:
                if geo_spatial_attrs[key] is not None:
                    if not copied:
                        dataset = dataset.copy()
                        copied = True
                    dataset.attrs[key] = geo_spatial_attrs[key]

    lon_min = dataset.attrs.get('geospatial_lon_min')
    lat_min = dataset.attrs.get('geospatial_lat_min')
    lon_max = dataset.attrs.get('geospatial_lon_max')
    lat_max = dataset.attrs.get('geospatial_lat_max')

    if lon_min is not None and lat_min is not None and lon_max is not None and lat_max is not None:

        if not copied:
            dataset = dataset.copy()

        dataset.attrs['geospatial_bounds'] = 'POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))'. \
            format(lon_min, lat_min, lon_min, lat_max, lon_max, lat_max, lon_max, lat_min, lon_min, lat_min)

        # Determination of the following attributes from introspection in a general
        # way is ambiguous, hence it is safer to drop them than to risk preserving
        # out of date attributes.
        drop = ['geospatial_bounds_crs', 'geospatial_bounds_vertical_crs',
                'geospatial_vertical_min', 'geospatial_vertical_max',
                'geospatial_vertical_positive', 'geospatial_vertical_units',
                'geospatial_vertical_resolution']

        for key in drop:
            dataset.attrs.pop(key, None)

    return dataset


def _get_geo_spatial_cf_attrs_from_var(dataset: xr.Dataset, var_name: str, allow_point: bool = False) -> Optional[dict]:
    """
    Get spatial boundaries, resolution and units of the given dimension of the given
    dataset. If the 'bounds' are explicitly defined, these will be used for
    boundary calculation, otherwise it will rest purely on information gathered
    from 'dim' itself.

    :param dataset: The dataset
    :param var_name: The variable/dimension name.
    :param allow_point: True, if it is ok to have no actual spatial extent.
    :return: A dictionary {'attr_name': attr_value}
    """

    if var_name not in dataset:
        return None

    var = dataset[var_name]

    if 'bounds' in var.attrs:
        # According to CF Conventions the corresponding 'bounds' coordinate variable name
        # should be in the attributes of the coordinate variable
        bnds_name = var.attrs['bounds']
    else:
        # If 'bounds' attribute is missing, the bounds coordinate variable may be named "<dim>_bnds"
        bnds_name = '%s_bnds' % var_name

    dim_var = None

    if bnds_name in dataset:
        bnds_var = dataset[bnds_name]
        if len(bnds_var.shape) == 2 and bnds_var.shape[0] > 0 and bnds_var.shape[1] == 2:
            dim_var = bnds_var
            dim_res = abs(bnds_var.values[0][1] - bnds_var.values[0][0])
            if bnds_var.shape[0] > 1:
                dim_min = min(bnds_var.values[0][0], bnds_var.values[-1][1])
                dim_max = max(bnds_var.values[0][0], bnds_var.values[-1][1])
            else:
                dim_min = min(bnds_var.values[0][0], bnds_var.values[0][1])
                dim_max = max(bnds_var.values[0][0], bnds_var.values[0][1])

    if dim_var is None:
        if len(var.shape) == 1 and var.shape[0] > 0:
            if var.shape[0] > 1:
                dim_var = var
                dim_res = abs(var.values[1] - var.values[0])
                dim_min = min(var.values[0], var.values[-1]) - 0.5 * dim_res
                dim_max = max(var.values[0], var.values[-1]) + 0.5 * dim_res
            elif len(var.values) == 1 and allow_point:
                dim_var = var
                # Actually a point with no extent
                dim_res = 0.0
                dim_min = var.values[0]
                dim_max = var.values[0]

    if dim_var is None:
        # Cannot determine spatial extent for variable/dimension var_name
        return None

    if 'units' in var.attrs:
        dim_units = var.attrs['units']
    else:
        dim_units = None

    res_name = 'geospatial_{}_resolution'.format(var_name)
    min_name = 'geospatial_{}_min'.format(var_name)
    max_name = 'geospatial_{}_max'.format(var_name)
    units_name = 'geospatial_{}_units'.format(var_name)

    geo_spatial_attrs = dict()
    # noinspection PyUnboundLocalVariable
    geo_spatial_attrs[res_name] = float(dim_res)
    # noinspection PyUnboundLocalVariable
    geo_spatial_attrs[min_name] = float(dim_min)
    # noinspection PyUnboundLocalVariable
    geo_spatial_attrs[max_name] = float(dim_max)
    geo_spatial_attrs[units_name] = dim_units

    return geo_spatial_attrs


def init_plugin():
    register_input_processor(DefaultInputProcessor())
