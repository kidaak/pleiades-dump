
import codecs
import cStringIO
import csv
import datetime
import logging
import re
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
        self.writer.writerow([self._encode(str(s).strip()) for s in row])
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
    try:
        return rec.reprPt[1] 
    except:
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

def geoContext(rec, catalog):
    note = rec.getModernLocation
    if not note:
        note = rec.Description or ""
        match = re.search(r"cited: BAtlas (\d+) (\w+)", note)
        if match:
            note = "Barrington Atlas grid %s %s" % (
                match.group(1), match.group(2).capitalize())
        else:
            note = ""
        note = unicode(note.replace(unichr(174), unichr(0x2194)))
        note = note.replace(unichr(0x2192), unichr(0x2194))
    return note

def getRating(rec, catalog):
    rid = rec.getRID()
    # A small number of records have no metadata column, but have index data.
    return rec.average_rating or catalog._catalog.getIndex("average_rating"
        ).getEntryForObject(rid, default=(0.0, 0))

common_schema = dict(
    id=lambda x, y: x.id,
    title=lambda x, y: x.Title,
    description=lambda x, y: x.Description,
    uid=lambda x, y: x.UID,
    path=lambda x, y: x.getPath().replace('/plone', ''),
    creators=lambda x, y: ', '.join(x.listCreators),
    created=lambda x, y: x.created.HTML4(),
    modified=lambda x, y: x.modified.HTML4(),
    timePeriods=getTimePeriods,
    timePeriodsKeys=getTimePeriodsKeys,
    timePeriodsRange=lambda x, y: None,
    minDate=lambda x, y: None,
    maxDate=lambda x, y: None,
    locationPrecision=location_precision,
    reprLatLong=lambda x, y: None,
    reprLat=lambda x, y: None,
    reprLong=lambda x, y: None,
    bbox=lambda x, y: ", ".join(map(str, x.bbox or [])),
    tags=lambda x, y: ", ".join(x.Subject),
    currentVersion=lambda x, y: x.currentVersion,
    )

locations_schema = common_schema.copy()
locations_schema.update(
    pid=lambda x, y: x.getPath().split('/')[3],
    geometry=lambda x, y: dumps(x.zgeo_geometry or None),
    featureTypes=lambda x, y: ', '.join(x.getFeatureType),
    avgRating=lambda x, y: getRating(x, y)[0],
    numRatings=lambda x, y: getRating(x, y)[1]
    )

names_schema = common_schema.copy()
names_schema.update(
    pid=lambda x, y: x.getPath().split('/')[3],
    nameAttested=lambda x, y: x.getNameAttested or None,
    nameLanguage=lambda x, y: x.getNameLanguage,
    nameTransliterated=lambda x, y: x.Title,
    extent=lambda x, y: dumps(x.zgeo_geometry or None),
    avgRating=lambda x, y: getRating(x, y)[0],
    numRatings=lambda x, y: getRating(x, y)[1]
    )

places_schema = common_schema.copy()
places_schema.update(
    featureTypes=lambda x, y: ', '.join(x.getFeatureType),
    geoContext=geoContext,
    extent=lambda x, y: dumps(x.zgeo_geometry or None)
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
    
    vocabs = getToolByName(context, 'portal_vocabularies')
    tp_vocab = vocabs.getVocabularyByName('time-periods').getTarget()
    tp_ranges = periodRanges(tp_vocab)

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
            query.update(
                path={'query': '/plone/places', 'depth': 2},
                review_state='published' )
        query.update(kwextras)
        results = catalog(query)
    writer = UnicodeWriter(sys.stdout)
    keys = sorted(schema.keys())
    writer.writerow(keys)
    if include_features:
        schema['pid'] = getFeaturePID
    for b in results:

        # representative point
        try:
            lon, lat = map(float, b.reprPt[0])
            precision = b.reprPt[1]
            schema['reprLat'] = lambda a, b: str(lat)
            schema['reprLong'] = lambda a, b: str(lon)
            schema['reprLatLong'] = lambda a, b: "%f,%f" % (lat, lon)
        except:
            log.warn("Unlocated: %s" % b.getPath())

        # dates
        years = []
        for tp in getattr(b, 'getTimePeriods', []):
            if tp:
                years.extend(list(tp_ranges[tp]))
        if len(years) >= 2:
            dmin, dmax = min(years), max(years)
            schema['minDate'] = lambda a, b: str(dmin)
            schema['maxDate'] = lambda a, b: str(dmax)
            schema['timePeriodsRange'] = lambda a, b: "%.1f,%.1f" % (dmin, dmax)

        writer.writerow([schema[k](b, catalog) or "" for k in keys])

def secure(context, username):
    membership = getToolByName(context, 'portal_membership')
    user=membership.getMemberById(username).getUser()
    newSecurityManager(None, user)

