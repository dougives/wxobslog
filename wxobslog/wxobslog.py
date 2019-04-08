import os
import cmd
import geojson
from urllib.parse import urljoin
import requests
from warnings import warn
from dateutil.tz import gettz
import dateutil.parser
from datetime import timedelta
import enum
import pkg_resources
from threading import Event, Thread

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

class WxObserverLogger(cmd.Cmd):
    prompt = 'wxobslog> '

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
        station_id = Column(String(4), ForeignKey('stations.id'), primary_key=True)
        station = relationship('Station', back_populates='observations')
        timestamp = Column(DateTime, primary_key=True)
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
                and self.station_id == other.station_id \
                and self.timestamp == other.timestamp
        def __ne__(self, other):
            return not self.__eq__(other)
        def __repr__(self):
            return f'<Observation({self.station} {self.timestamp})>'

    class TrackedStations(Model):
        __tablename__ = 'tracked_stations'
        station_id = Column(String(4), ForeignKey('stations.id'), primary_key=True)
        station = relationship('Station')
        def __repr__(self):
            return f'<TrackedStation({self.station})>'

    def __init__(self, db_connection_string, update_interval=1800.00):
        super(WxObserverLogger, self).__init__()
        self._engine = create_engine(db_connection_string)
        WxObserverLogger.Model.metadata.create_all(self._engine)
        self._session = sessionmaker(bind=self._engine)()
        self.update_interval = update_interval
        self._stop_update_timer = self._update_thread()

    def _update(self):
        [ self.log_latest_station_observation(t.station_id)
            for t in self._session.query(
                WxObserverLogger.TrackedStations).all() ]

    def _update_thread(self):
        stopped = Event()
        def target():
            while not stopped.wait(self.update_interval):
                self._update()
        Thread(target=target, daemon=True).start()
        return stopped.set

    @staticmethod
    def _api_get(endpoint, *args):
        url = urljoin(
            WxObserverLogger.API_BASE,
            endpoint) \
                if not args \
                else urljoin(
                    WxObserverLogger.API_BASE,
                    f'{endpoint}/' + '/'.join( str(arg) for arg in args ))
        headers = {
            'User-Agent': WxObserverLogger.USER_AGENT,
        }
        response = requests.get(url, headers=headers)
        if response.status_code != requests.codes.ok:
            warn(
                f'Received status code {response.status_code} '\
                f'when requesting {url}')
            return
        return geojson.loads(response.text)

    @staticmethod
    def _parse_station(feature):
        props = feature['properties']
        coords = feature['geometry']['coordinates']
        return WxObserverLogger.Station(
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
            WxObserverLogger.Station).filter(
                WxObserverLogger.Station.id == station_id).first()

    def _get_last_logged_station_observation(self, station):
        # what the fuck
        # SELECT stations.id = observations.station_id AS observations 
        # FROM stations, observations
        # obs = self._session.query(
        #     WxObserverLogger.Station.observations).order_by(
        #         desc(WxObserverLogger.Observation.timestamp)).first()
        obs = self._session.query(WxObserverLogger.Observation).filter_by(
            station_id=station.id).order_by(
                desc(WxObserverLogger.Observation.timestamp)).first()
        return obs

    def update_all_stations(self):
        obj = WxObserverLogger._api_get('stations')
        if not obj:
            warn('Failed to update all stations, error requesting station list.')
            return
        self._session.query(WxObserverLogger.Station).delete()
        new_stations = []
        for feature in obj['features']:
            new_station = WxObserverLogger._parse_station(feature)
            old_station = self._get_station_by_id(new_station.id)
            if not old_station:
                new_stations.append(
                    WxObserverLogger._parse_station(feature))
                continue
            WxObserverLogger._update_station_fields(
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
        station_id = WxObserverLogger._normalize_station_id(station_id)
        if not station_id:
            warn('Failed to update station, invalid station id.')
            return
        new_station = WxObserverLogger._api_get('stations', station_id)
        if not new_station:
            warn('Failed to update station, error requesting station.')
            return
        old_station = self._get_station_by_id(new_station.id)
        if not old_station:
            self._session.add(
                WxObserverLogger._parse_station(new_station))
            self._session.commit()
            return
        self._update_station_fields(old_station, new_station)
        self._session.commit()

    def _find_or_update_station_by_id(self, station_id, warning_msg_verb):
        station_id = WxObserverLogger._normalize_station_id(station_id)
        if not station_id:
            warn(f'Failed to {warning_msg_verb}, invalid station id.')
            return
        station = self._get_station_by_id(station_id)
        if not station:
            self.update_station(station_id)
        station = self._get_station_by_id(station_id)
        if not station:
            warn(f'Failed to {warning_msg_verb}, station {station_id} not found.')
            return
        return station

    @staticmethod
    def _parse_observation(station, props):
        return WxObserverLogger.Observation(
            station_id=station.id,
            station=station,
            timestamp=dateutil.parser.isoparse(props['timestamp']).replace(tzinfo=None),
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
        station = self._find_or_update_station_by_id(
            station_id,
            f'log latest station observation for {station_id}')
        if not station:
            return
        obj = WxObserverLogger._api_get(
            'stations', station_id, 'observations', 'latest')
        if not station:
            warn('Failed to log last station observation, error requesting requesting last observation.')
            return
        last_logged_obs = self._get_last_logged_station_observation(station)
        obs = WxObserverLogger._parse_observation(station, obj['properties'])
        if obs == last_logged_obs:
            del obs
            self._session.rollback()
            return
        station.observations.append(obs)
        self._session.commit()

    def _get_tracked_station_by_id(self, station_id):
        return self._session.query(
            WxObserverLogger.TrackedStations).filter_by(
                station_id=station_id).one_or_none()

    def add_tracked_station(self, station_id):
        station = self._find_or_update_station_by_id(
            station_id,
            f'add tracked station {station_id}')
        if not station:
            return
        already_tracked = self._get_tracked_station_by_id(station_id)
        if already_tracked:
            return
        tracked_station = WxObserverLogger.TrackedStations(
            station_id=station_id,
            station=station)
        self._session.add(tracked_station)
        self._session.commit()

    def remove_tracked_station(self, station_id):
        tracked_station = self._get_tracked_station_by_id(station_id)
        if not tracked_station:
            warn(f'Cannot remove tracked station {station_id}, because it is not currently being tracked.')
            return
        self._session.delete(tracked_station)
        self._session.commit()

    def do_track(self, station_id):
        self.add_tracked_station(station_id)
    def do_untrack(self, station_id):
        self.remove_tracked_station(station_id)
    def do_list(self, arg):
        [ print(t.station_id)
            for t in self._session.query(
                WxObserverLogger.TrackedStations).all() ]
    def do_update(self, arg):
        self._update()
    def do_interval(self, arg):
        self.update_interval = float(arg)
    def do_quit(self, arg):
        raise KeyboardInterrupt
    def close(self):
        self._stop_update_timer()
        self._session.close()

def main():
    wxobslogger= WxObserverLogger(
        os.environ['WXOBSLOG_DB_CONNECTION_STRING'])
    try:
        wxobslogger.cmdloop()
    except KeyboardInterrupt:
        wxobslogger.close()
        print()
    return 0

if __name__ == '__main__':
    exit(main())
