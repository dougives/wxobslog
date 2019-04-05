from setuptools import setup

setup(
   name='wxobslog',
   version='0.0.0-dev',
   description='NWS Station Observation Logger',
   author='Doug Ives',
   author_email='wx@dou.gives',
   packages=['wxobslog'],
   install_requires=[
       'SqlAlchemy', 
       'requests', 
       'python-dateutil',
       'geojson',
       'geoalchemy2',
       'psycopg2-binary',
    ],
)