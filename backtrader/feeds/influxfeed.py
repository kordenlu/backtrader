#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from __future__ import absolute_import, division, print_function, unicode_literals

import backtrader as bt
import backtrader.feed as feed
from ..utils import date2num
import datetime as dt
import logging
import time

# 配置日志
logger = logging.getLogger(__name__)

TIMEFRAMES = dict(
    (
        (bt.TimeFrame.Seconds, "s"),
        (bt.TimeFrame.Minutes, "m"),
        (bt.TimeFrame.Days, "d"),
        (bt.TimeFrame.Weeks, "w"),
        (bt.TimeFrame.Months, "m"),
        (bt.TimeFrame.Years, "y"),
    )
)


class InfluxDB(feed.DataBase):
    frompackages = (
        ("influxdb_client", [("InfluxDBClient", "idbclient")]),
        ("influxdb_client.client.exceptions", "InfluxDBError"),
    )

    params = (
        ("url", "http://localhost:8086"),  # InfluxDB 2.0 requires a URL
        (
            "token",
            "",
        ),  # Authentication token
        ("org", "yml"),  # Organization
        ("bucket", "hloc"),  # Bucket (database in InfluxDB 1.x terms)
        ("timeframe", bt.TimeFrame.Days),
        ("startdate", None),
        ("enddate", dt.datetime.now().strftime("%Y-%m-%d")),
        ("symbol_code", "600519"),  # Symbol code
        ("market", "SH"),  # Market
        ("high", "high"),
        ("low", "low"),
        ("open", "open"),
        ("close", "close"),
        ("volume", "volume"),
        # ("ointerest", "oi"),
        ("measurement", "hloc_data"),  # Measurement name (table in InfluxDB)
    )

    def start(self):
        super(InfluxDB, self).start()
        try:
            self.client = idbclient(url=self.p.url, token=self.p.token, org=self.p.org)
            self.query_api = self.client.query_api()  # Obtain the Query API
        except InfluxDBError as err:
            print("Failed to establish connection to InfluxDB: %s" % err)
            return

        tf = "{multiple}{timeframe}".format(
            multiple=(self.p.compression if self.p.compression else 1),
            timeframe=TIMEFRAMES.get(self.p.timeframe, "d"),
        )

        if not self.p.startdate:
            st = "-30d"  # default to 30 days
        else:
            st = self.p.startdate

        # Flux query
        query = """
            from(bucket: "{bucket}")
              |> range(start: {startdate},end: {enddate})
              |> filter(fn: (r) => r._measurement == "{measurement}")
              |> filter(fn: (r) => r.market == "{market}" and r.symbol_code == "{symbol_code}")
              |> filter(fn: (r) => r._field == "{open_f}" or r._field == "{high_f}" or r._field == "{low_f}" or r._field == "{close_f}" or r._field == "{vol_f}")
              |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
              |> yield(name: "mean")
        """.format(
            bucket=self.p.bucket,
            startdate=st,
            measurement=self.p.measurement,
            market=self.p.market,
            symbol_code=self.p.symbol_code,
            open_f=self.p.open,
            high_f=self.p.high,
            low_f=self.p.low,
            close_f=self.p.close,
            vol_f=self.p.volume,
            # oi_f=self.p.ointerest,
        )

        try:
            # Execute the query
            result = self.query_api.query(query)
            self.dbars = []
            for table in result:
                for record in table.records:
                    self.dbars.append(record.values)

            self.biter = iter(self.dbars)

        except InfluxDBError as err:
            print("InfluxDB query failed: %s" % err)
            return

    def stop(self):
        """Clean up resources when feed is no longer needed"""
        super(InfluxDB, self).stop()
        if self.client:
            # 确保关闭连接
            try:
                self.client.close()
                logger.info("InfluxDB client connection closed")
            except Exception as e:
                logger.error(f"Error closing InfluxDB client: {e}")

    def _load(self):
        try:
            bar = next(self.biter)
        except StopIteration:
            return False

        try:
            if isinstance(bar["_time"], str):
                for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                    try:
                        dt_object = dt.datetime.strptime(bar["_time"], fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return False
            else:
                dt_object = bar["_time"]
            # Check if bar["_time"] is already a datetime object

            self.l.datetime[0] = date2num(dt_object)

            self.l.open[0] = bar[self.p.open]
            self.l.high[0] = bar[self.p.high]
            self.l.low[0] = bar[self.p.low]
            self.l.close[0] = bar[self.p.close]
            self.l.volume[0] = bar[self.p.volume]

            return True
        except (KeyError, ValueError) as e:
            logger.error(f"Error loading data: {e}")
            return False
