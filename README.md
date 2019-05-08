# wxobslog
Regularly logs weather observations from selected stations using the [NWS API](https://www.weather.gov/documentation/services-web-api).

## Database Configuration
Postgres with the PostGIS extention is required to run wxobslog. Most cloud providers offer Postgres with the PostGIS extention already installed. You must enable it with the query:
```
CREATE EXTENSION postgis;
```
The environemt variable `WXOBSLOG_DB_CONNECTION_STRING` needs to be set for your desired database connection configuration. For example:
```
$ WXOBSLOG_DB_CONNECTION_STRING=postgresql://wxobslog:password@db.example.com:5432/wxobslog?sslmode=require python3 -m wxobslog
```
SQLAlchemy documentation for database connection strings can be found [here](https://docs.sqlalchemy.org/en/13/core/engines.html).

## Station IDs
Station IDs are four letter codes which represent a specific NWS observation station. A list of all stations can be retrieved with:
```
$ curl -X GET "https://api.weather.gov/stations" -H  "accept: application/geo+json"
```
A list of stations for a specific state can be retrieved by providing a two-letter abbreviated `state` parameter value:
```
$ curl -X GET "https://api.weather.gov/stations?state=IL" -H  "accept: application/geo+json"
```
Additionaly, station ids are shown at the top of the regular NWS forecast page, in parenthesis:
![forecast header example](https://dou.gives/forecast_header.png)

## Commands
The prompt `wxobslog>` will show after wxobslog is started. The prompt accepts these commands:

- track \<station id\>
    - Starts tracking observations from the given station id.
- untrack \<station id\>
    - Stops tracking observations from the given station id. 
- list
    - Lists all station id's currently being tracked.
- update
    - Forces an update of all tracked station ids.
- interval
    - Sets the update interval to check for new observations.
- quit
    - Exits wxobslog.

## Schema
Here is an example of a couple log entries:
```
wxobslog=# \x on
Expanded display is on.
wxobslog=# select * from observations;
-[ RECORD 1 ]-----------------+-----------------------------
station_id                    | KORD
timestamp                     | 2019-05-08 18:51:00
barometric_pressure           | 101420
dewpoint                      | 5.60000000000002
heat_index                    | 
max_temperature_last_24_hours | 
min_temperature_last_24_hours | 
precipitation_last_hour       | 
precipitation_last_3_hours    | 
precipitation_last_6_hours    | 
raw_message                   | KORD 081851Z 09013KT 10SM BKN055 BKN080 OVC250 13/06 A2995 RMK AO2 SLP145 T01330056
relative_humidity             | 59.6008796741699
sea_level_pressure            | 101450
temperature                   | 13.3
text_description              | Cloudy
visibility                    | 16090
wind_chill                    | 
wind_direction                | 90
wind_gust                     | 
wind_speed                    | 7
-[ RECORD 2 ]-----------------+-----------------------------
station_id                    | KJFK
timestamp                     | 2019-05-08 19:51:00
barometric_pressure           | 102340
dewpoint                      | 9.40000000000003
heat_index                    | 
max_temperature_last_24_hours | 
min_temperature_last_24_hours | 
precipitation_last_hour       | 
precipitation_last_3_hours    | 
precipitation_last_6_hours    | 
raw_message                   | KJFK 081951Z 14011KT 10SM FEW050 FEW100 SCT250 17/09 A3022 RMK AO2 SLP232 T01720094
relative_humidity             | 60.1341856232283
sea_level_pressure            | 102320
temperature                   | 17.2
text_description              | Partly Cloudy
visibility                    | 16090
wind_chill                    | 
wind_direction                | 140
wind_gust                     | 
wind_speed                    | 6
```

Not all observations will contain every column field. Fields like `max_temperature_last_24_hours` are only updated periodically. Fields like `wind_chill` will only be updated when relevant.

All units are SI; that is: pascal, celsius, meters, meters-per-second, etc. Azimuths are measured in degrees.

Timestamps are normalized to UTC.
