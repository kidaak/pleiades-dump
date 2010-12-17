
from pleiades.dump import dump_catalog, locations_schema

if __name__ == '__main__':
    dump_catalog(app['plone'], 'Location', locations_schema)

