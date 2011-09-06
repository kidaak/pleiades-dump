
import codecs
import cStringIO
import csv
import datetime
import logging
import sys

from simplejson import dumps
from AccessControl.SecurityManagement import newSecurityManager
from Products.CMFCore.utils import getToolByName

from pleiades.geographer.geo import zgeo_geometry_centroid
from Products.PleiadesEntity.time import periodRanges

log = logging.getLogger('pleiades.dump')

timePeriods = {
    "early-geometric": (-900, -850),
    "middle-geometric": (-850, -750),
    "archaic": (-750, -550),
    "classical": (-550, -330),
    "hellenistic-republican": (-330, -30),
    "roman": (30, 300),
    "late-antique": (300, 640),
    "mediaeval-byzantine": (641, 1453),
    "modern": (1700, 2100)
    }

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

    def _encode(self, s):
        try:
            return s.encode('utf-8')
        except:
            return s
        
    def writerow(self, row):
        self.writer.writerow([self._encode(s.strip()) for s in row])
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
    v = catalog._catalog.getIndex('location_precision').getEntryForObject(
        rec.getRID(), default=['unlocated'])
    try:
        return v[0]
    except IndexError:
        return 'unlocated'

def getTimePeriods(rec, catalog):
    periods = getattr(rec, 'getTimePeriods', None)
    try:
        return ''.join(v[0].upper() for v in periods)
    except:
        return ''

def getTimePeriodsKeys(rec, catalog):
    periods = getattr(rec, 'getTimePeriods', None)
    try:
        return ','.join(v for v in periods)
    except:
        return ''

def getDates(rec, catalog):
    periods = ["archaic"] #getattr(rec, 'getTimePeriods', None)
    if periods:
        f, t = zip(*[timePeriods[v] for v in periods])
        return "%d,%d" % (min(f), max(t))
    else:
        return None

def getDates2(rec, catalog):
    """Nominal temporal range, not accounting for level of confidence"""
    vocab = getToolByName(
        catalog, 'portal_vocabularies'
        ).getVocabularyByName('time-periods').getTarget()
    ranges = periodRanges(vocab)
    years = []
    for tp in getattr(rec, 'getTimePeriods', []):
        if tp:
            years.extend(list(ranges[tp]))
    if len(years) >= 2:
        return "%.1f,%.1f" % (min(years), max(years))
    else:
        return None

def getGeometry(rec, catalog):
    geo = None
    try:
        geo = dict(rec.zgeo_geometry.items())
        geo['relation'] = location_precision(rec, catalog)
    except:
        log.warn("Unlocated: %s" % rec.getPath())
    return dumps(geo)

def getReprLatLong(rec, catalog):
    try:
        lon, lat = zgeo_geometry_centroid(rec)
        return "%f,%f" % (lat, lon)
    except:
        log.warn("Unlocated: %s" % rec.getPath())

places_schema = dict(
    id=lambda x, y: x.id,
    title=lambda x, y: x.Title,
    description=lambda x, y: x.Description,
    uid=lambda x, y: x.UID,
    path=lambda x, y: x.getPath().replace('/plone', ''),
    creators=lambda x, y: ', '.join(x.listCreators),
    created=lambda x, y: x.created.HTML4(),
    modified=lambda x, y: x.modified.HTML4(),
    featureTypes=lambda x, y: ', '.join(x.getFeatureType),
    timePeriods=getTimePeriods,
    timePeriodsKeys=getTimePeriodsKeys,
    timePeriodsRange=getDates2,
    locationPrecision=location_precision,
    reprLatLong=getReprLatLong,
    )

names_schema = dict(
    id=lambda x, y: x.id,
    pid=lambda x, y: x.getPath().split('/')[3],
    title=lambda x, y: x.Title,
    description=lambda x, y: x.Description,
    uid=lambda x, y: x.UID,
    path=lambda x, y: x.getPath().replace('/plone', ''),
    creators=lambda x, y: ', '.join(x.listCreators),
    created=lambda x, y: x.created.HTML4(),
    modified=lambda x, y: x.modified.HTML4(),
    nameAttested=lambda x, y: x.getNameAttested or None,
    nameLanguage=lambda x, y: x.getNameLanguage,
    nameTransliterated=lambda x, y: x.Title,
    timePeriods=getTimePeriods,
    timePeriodsKeys=getTimePeriodsKeys,
    timePeriodsRange=getDates2,
    locationPrecision=location_precision,
    reprLatLong=getReprLatLong,
    )

locations_schema = dict(
    id=lambda x, y: x.id,
    pid=lambda x, y: x.getPath().split('/')[3],
    title=lambda x, y: x.Title,
    description=lambda x, y: x.Description,
    uid=lambda x, y: x.UID,
    path=lambda x, y: x.getPath().replace('/plone', ''),
    creators=lambda x, y: ', '.join(x.listCreators),
    created=lambda x, y: x.created.HTML4(),
    modified=lambda x, y: x.modified.HTML4(),
    geometry=getGeometry,
    timePeriods=getTimePeriods,
    timePeriodsKeys=getTimePeriodsKeys,
    timePeriodsRange=getDates2,
    locationPrecision=location_precision,
    reprLatLong=getReprLatLong,
    )

def getFeaturePID(b, catalog):
    container =  b.getPath().split('/')[2]
    if container == 'places':
        return b.getPath().split('/')[3]
    feature = b.getObject()
    places = feature.getPlaces()
    if places:
        return places[0].id
    else:
        return '-1'

def dump_catalog(context, portal_type, cschema, **extras):
    schema = cschema.copy()
    include_features = False
    kwextras = extras.copy()
    if 'include_features' in kwextras:
        include_features = True
        del kwextras['include_features']
    catalog = getToolByName(context, 'portal_catalog')
    if 'collection_path' in extras:
        collection = catalog(
            path={'query': extras['collection_path'], 'depth': 0}
            )[0].getObject()
        targets = collection.queryCatalog()
        results = []
        for target in targets:
            results += catalog(
                path=target.getPath(), portal_type=portal_type, **kwextras)
    else:
        query = {'portal_type': portal_type}
        if not include_features:
            query.update(path={'query': '/plone/places', 'depth': 2})
        query.update(kwextras)
        results = catalog(query)
    writer = UnicodeWriter(sys.stdout)
    keys = sorted(schema.keys())
    writer.writerow(keys)
    if include_features:
        schema['pid'] = getFeaturePID
    for b in results:
        writer.writerow([schema[k](b, catalog) or "" for k in keys])

def secure(context, username):
    membership = getToolByName(context, 'portal_membership')
    user=membership.getMemberById(username).getUser()
    newSecurityManager(None, user)

