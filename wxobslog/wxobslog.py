import os
import cmd
import geojson
from urllib.parse import urljoin
import requests
from warnings import warn
from dataclasses import dataclass
from dateutil.tz import gettz
import enum
import pkg_resources

from sqlalchemy import create_engine, Table, Column, Integer, String, Float, DateTime, Enum
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from geoalchemy2 import Geometry


__PROGRAM_NAME__ = pkg_resources.require("wxobslog")[0].project_name
__VERSION__ = pkg_resources.require("wxobslog")[0].version

@enum.unique
class CloudCover(enum.Enum):
    SkyClear            = 'SKC'
    NoCloudDetected     = 'NCD'
    Clear               = 'CLR'
    NoSignificantCloud  = 'NSC'
    Few                 = 'FEW'
    Scattered           = 'SCT'
    Broken              = 'BKN'
    Overcast            = 'OVC'
    VerticalVisibility  = 'VV'

class NationalWeatherService:
    API_BASE = 'https://api.weather.gov'
    USER_AGENT = f'{__PROGRAM_NAME__}/{__VERSION__} (wx@dou.gives)'

    Model = declarative_base()

    class Station(Model):
        __tablename__ = 'stations'
        id = Column(String(4), primary_key=True)
        name = Column(String(128), nullable=False)
        coordinates = Column(Geometry('POINT'), nullable=False)
        elevation = Column(Float, nullable=False)
        timezone = Column(String(64), nullable=False)
        observations = relationship('Observation', back_populates='station')
        def __repr__(self):
            return f'<Station({self.id})>'

    class Observation(Model):
        __tablename__ = 'observations'
        station = relationship('Station', back_populates='observations')
        timestamp = Column(DateTime, primary_key=True, timezone=True)
        barometric_pressure = Column(Float)
        cloud_cover = Column(Enum(CloudCover))
        cloud_base = Column(Integer)
        dewpoint = Column(Float)
        heat_index = Column(Float)
        max_temperature_last_24_hours = Column(Float)
        min_temperature_last_24_hours = Column(Float)
        precipitation_last_hour = Column(Float)
        precipitation_last_3_hours = Column(Float)
        precipitation_last_6_hours = Column(Float)
        present_weather = Column(String(32))
        raw_message = Column(String(256))
        relative_humidity = Column(Float)
        sea_level_pressure = Column(Float)
        temperature = Column(Float)
        text_description = Column(String(256))
        visibility = Column(Integer)
        wind_chill = Column(Float)
        wind_direction = Column(Integer)
        wind_gust = Column(Integer)
        wind_speed = Column(Integer)
        def __repr__(self):
            return f'<Observation({self.station} {self.timestamp})>'

    def __init__(self, db_connection_string):
        self._engine = create_engine(db_connection_string)
        NationalWeatherService.Model.metadata.create_all(self._engine)
        self._session = sessionmaker(bind=self._engine)()

    @staticmethod
    def _api_get(endpoint, *args):
        url = urljoin(
            NationalWeatherService.API_BASE,
            endpoint + '/'.join( str(arg) for arg in args ))
        headers = {
            'User-Agent': NationalWeatherService.USER_AGENT,
        }
        response = requests.get(url, headers=headers)
        if response.status_code != requests.codes.ok:
            warn(
                f'Received status code {response.status_code} '\
                f'when requesting {url}')
            return
        return geojson.loads(response.text)

    def update_all_stations(self):
        obj = NationalWeatherService._api_get('stations')
        if not obj:
            warn('Failed to retrieve station listing.')
            return
        self._session.query(NationalWeatherService.Station).delete()
        for feature in obj['features']:
            props = feature['properties']
            coords = feature['geometry']['coordinates']
            self._session.add(NationalWeatherService.Station(
                id=props['stationIdentifier'],
                name=props['name'],
                coordinates=f'POINT({coords[0]} {coords[1]})',
                elevation=props['elevation']['value'],
                timezone=props['timeZone']))
            self._session.flush()
        self._session.commit()

    def update_station(self, station_id):
        station_id = station_id.upper()
        if len(station_id) != 4:
            warn('Station id must be four characters in length.')
            return
        if station_id[0] != 'K':
            warn('Station id must begin with \'K\'.')
            return
        obj = NationalWeatherService._api_get('stations', station_id)

    def _get_station_by_id(self, station_id):
        return self._session.query(
            NationalWeatherService.Station).first(
                NationalWeatherService.Station.id == station_id).one_or_none()

    def add_tracked_station(self, station_id):
        station = self._get_station_by_id(station_id)
        if not station:
            pass
        assert False
        

def main():
    nws = NationalWeatherService(os.environ['WXOBSLOG_DB_CONNECTION_STRING'])
    nws.update_all_stations()
    return 0

if __name__ == '__main__':
    exit(main())
