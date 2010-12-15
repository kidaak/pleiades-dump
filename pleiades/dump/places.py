
from pleiades.dump import dump_catalog, places_schema

if __name__ == '__main__':
    dump_catalog(app['plone'], 'Place', places_schema)

