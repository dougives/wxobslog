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

from sqlalchemy import desc, create_engine, Table, Column, ForeignKey, Integer, String, Float, DateTime, Enum
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from geoalchemy2 import Geometry

_package__info = pkg_resources.require("wxobslog")[0]

_project_name = _package__info.project_name
_version = _package__info.version

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
    USER_AGENT = f'{_project_name}/{_version} (wx@dou.gives)'

    Model = declarative_base()

    class Station(Model):
        __tablename__ = 'stations'
        id = Column(String(4), primary_key=True)
        name = Column(String(128), nullable=False)
        coordinates = Column(Geometry('POINT'), nullable=False)
        elevation = Column(Float, nullable=False)
        timezone = Column(String(64), nullable=False)
        observations = relationship('Observation', back_populates='station')
        def __eq__(self, other):
            return other != None \
                and self.id == other.id \
                and self.coordinates == other.coordinates \
                and self.elevation == other.elevation \
                and self.timezone == other.timezone
        def __ne__(self, other):
            return not self.__eq__(other)
        def __repr__(self):
            return f'<Station({self.id})>'

    class Observation(Model):
        __tablename__ = 'observations'
        station_id = Column(String(4), ForeignKey('stations.id'))
        station = relationship('Station', back_populates='observations')
        timestamp = Column(DateTime, primary_key=True, timezone=True)
        barometric_pressure = Column(Float)
        #cloud_cover = Column(Enum(CloudCover))
        #cloud_base = Column(Integer)
        dewpoint = Column(Float)
        heat_index = Column(Float)
        max_temperature_last_24_hours = Column(Float)
        min_temperature_last_24_hours = Column(Float)
        precipitation_last_hour = Column(Float)
        precipitation_last_3_hours = Column(Float)
        precipitation_last_6_hours = Column(Float)
        #present_weather = Column(String(32))
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
        def __eq__(self, other):
            return other != None \
                and self.station == other.station \
                and self.timestamp == other.timestamp
        def __ne__(self, other):
            return not self.__eq__(other)
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
            endpoint) \
                if not args \
                else urljoin(
                    NationalWeatherService.API_BASE,
                    f'{endpoint}/' + '/'.join( str(arg) for arg in args ))
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

    @staticmethod
    def _parse_station(self, feature):
        props = feature['properties']
        coords = feature['geometry']['coordinates']
        return NationalWeatherService.Station(
            id=props['stationIdentifier'],
            name=props['name'],
            coordinates=f'POINT({coords[0]} {coords[1]})',
            elevation=props['elevation']['value'],
            timezone=props['timeZone'])
        
    @staticmethod
    def _update_station_fields(old, new):
        if new_station == old_station:
            return
        old_station.name = new_station.name
        old_station.coordinates = new_station.coordinates
        old_station.elevation = new_station.elevation
        old_station.timezone = new_station.timezone

    def _get_station_by_id(self, station_id):
        return self._session.query(
            NationalWeatherService.Station).filter(
                NationalWeatherService.Station.id == station_id).first()

    def _get_last_logged_station_observation(self, station):
        return self._session.query(
            NationalWeatherService.Station.observations).order_by(
                desc(NationalWeatherService.Observation.timestamp)).first()

    def update_all_stations(self):
        obj = NationalWeatherService._api_get('stations')
        if not obj:
            warn('Failed to update all stations, error requesting station list.')
            return
        self._session.query(NationalWeatherService.Station).delete()
        new_stations = []
        for feature in obj['features']:
            new_station = NationalWeatherService._parse_station(feature)
            old_station = self._get_station_by_id(new_station.id)
            if not old_station:
                new_stations.append(
                    NationalWeatherService._parse_station(feature))
                continue
            NationalWeatherService._update_station_fields(
                old_station, new_station)
            self._session.flush()
        self._session.add_all(new_stations)
        self._session.commit()

    @staticmethod
    def _normalize_station_id(station_id):
        station_id = station_id.upper()
        if len(station_id) != 4:
            warn('Station id must be four characters in length.')
            return
        if station_id[0] != 'K':
            warn('Station id must begin with \'K\'.')
            return
        return station_id

    def update_station(self, station_id):
        station_id = NationalWeatherService._normalize_station_id(station_id)
        if not station_id:
            warn('Failed to update station, invalid station id.')
            return
        new_station = NationalWeatherService._api_get('stations', station_id)
        if not station:
            warn('Failed to update station, error requesting station.')
            return
        old_station = self._get_station_by_id(new_station.id)
        if not old_station:
            self._session.add(new_station)
            self._session.commit()
            return
        self._update_station_fields(old_station, new_station)
        self._session.commit()

    @staticmethod
    def _parse_observation(station, props):
        return NationalWeatherService.Observation(
            station=station,
            timestamp=props['timestamp'],
            barometric_pressure=props['barometricPressure']['value'],
            #cloud_cover=CloudCover(props['cloudLayers']['amount']),
            #cloud_base=props['cloudLayers']['base']['value'],
            dewpoint=props['dewpoint']['value'],
            heat_index=props['heatIndex']['value'],
            max_temperature_last_24_hours=props['maxTemperatureLast24Hours']['value'],
            min_temperature_last_24_hours=props['minTemperatureLast24Hours']['value'],
            precipitation_last_hour=props['precipitationLastHour']['value'],
            precipitation_last_3_hours=props['precipitationLast3Hours']['value'],
            precipitation_last_6_hours=props['precipitationLast6Hours']['value'],
            # present_weather=props['presentWeather']['rawString'],
            raw_message=props['rawMessage'],
            relative_humidity=props['relativeHumidity']['value'],
            sea_level_pressure=props['seaLevelPressure']['value'],
            temperature=props['temperature']['value'],
            text_description=props['textDescription'],
            visibility=props['visibility']['value'],
            wind_chill=props['windChill']['value'],
            wind_direction=props['windDirection']['value'],
            wind_gust=props['windGust']['value'],
            wind_speed=props['windSpeed']['value'])

    def log_latest_station_observation(self, station_id):
        station_id = NationalWeatherService._normalize_station_id(station_id)
        if not station_id:
            warn('Failed to log last station observation, invalid station id.')
            return
        station = self._get_station_by_id(station_id)
        if not station:
            self.update_station(station_id)
        station = self._get_station_by_id(station_id)
        if not station:
            warn(f'Failed to log last station observation, station {station_id} not found.')
        obj = NationalWeatherService._api_get(
            'stations', station_id, 'observations', 'latest')
        if not station:
            warn('Failed to log last station observation, error requesting requesting last observation.')
            return
        last_logged_obs = self._get_last_logged_station_observation(station)
        obs = NationalWeatherService._parse_observation(station, obj['properties'])
        if obs == last_logged_obs:
            return
        station.observations.append(obs)
        self._session.commit()

    def add_tracked_station(self, station_id):
        station = self._get_station_by_id(station_id)
        if not station:
            pass
        assert False
        

def main():
    nws = NationalWeatherService(os.environ['WXOBSLOG_DB_CONNECTION_STRING'])
    nws.log_latest_station_observation('KORD')
    return 0

if __name__ == '__main__':
    exit(main())
