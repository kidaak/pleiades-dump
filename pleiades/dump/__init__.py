
import codecs
import cStringIO
import csv
import datetime
import logging

from Products.CMFCore.utils import getToolByName

log = logging.getLogger('pleiades.dump')

class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getencoder(encoding)

    def writerow(self, row):
        self.writer.writerow([s.encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder(data)[0]
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

def location_precision(rec, catalog):
    return catalog.getIndexDataForRID(rec.getRID()).get(
        'location_precision', ['unlocated'])[0]
    
schema = dict(
    id=lambda x, y: x.id,
    title=lambda x, y: x.Title,
    description=lambda x, y: x.Description,
    uid=lambda x, y: x.UID,
    path=lambda x, y: x.getPath().replace('/plone', ''),
    creators=lambda x, y: ', '.join(x.listCreators),
    created=lambda x, y: x.created.HTML4(),
    modified=lambda x, y: x.modified.HTML4(),
    featureTypes=lambda x, y: ', '.join(x.getFeatureType),
    locationPrecision=location_precision
    )

def dump_places(context):
    catalog = getToolByName(context, 'portal_catalog')
    cschema = catalog._catalog.schema.copy()
    results = catalog(portal_type=['Place'])
    filename = "pleiades-place-dump-%s.csv" % (
        datetime.datetime.now().strftime('%Y%m%d'))
    writer = UnicodeWriter(open(filename, 'wb'))
    keys = sorted(schema.keys())
    writer.writerow(keys)
    for b in results:
        writer.writerow([schema[k](b, catalog) for k in keys])

