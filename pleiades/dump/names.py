
from pleiades.dump import dump_catalog, names_schema

if __name__ == '__main__':
    dump_catalog(app['plone'], 'Name', names_schema)

