import cyclone.web, json
from twisted.internet.defer import maybeDeferred, inlineCallbacks, returnValue
from twisted.internet.threads import deferToThread

def stationProperties(s):
    return dict((k, getattr(s, k)) for k in
                "isCreator name idToken useQuickMix isQuickMix id".split())

def songProperties(s):
    return dict((k, getattr(s, k)) for k in
                'album artist artistMusicId audioUrl fileGain identity '
                'musicId rating stationId title userSeed songDetailURL '
                'albumDetailURL artRadio songType'.split())

def mpdCurrentSongProperties(s):
    out = s.copy()
    for intKey in ['id', 'pos', 'time']: # probably incomplete
        if intKey in out:
            out[intKey] = int(out[intKey])
    return out


class Resource(cyclone.web.RequestHandler):
    def get(self, *args):
        self.set_header("Content-Type", "application/json")
        return (maybeDeferred(self.getJson, *args)
                .addCallback(lambda j: self.write(json.dumps(j))))

    def mpd(self):
        return self.settings.mpdConnection.currentConnection

    def pandora(self):
        return self.settings.pandora

    def pandoraCall(self, method, *args):
        m = getattr(self.pandora(), method)
        return deferToThread(m, *args)

    def makeUri(self, rel):
        return self.settings.baseUri + rel


class Index(Resource):
    def getJson(self):
        out = {'connectedToMpd' : bool(self.mpd()),
               'stations' : self.makeUri('stations/'),
               'currentStation' : self.makeUri('currentStation'),
               }
        out.update(self.settings.feeder.moreStatus())
        return out
        
        
class Stations(Resource):
    def getJson(self):
        ret = []
        for s in self.pandora().stations:
            ret.append(stationProperties(s))
            ret[-1]['uri'] = self.makeUri('stations/%s/' % ret[-1]['id'])
        return {'stations' : ret}


class Station(Resource):
    def getJson(self, sid):
        def stn(s):
            return {'station' : stationProperties(s),
                    'play' : self.makeUri('currentStation')}
        return self.pandoraCall('get_station_by_id', sid).addCallback(stn)


class CurrentStation(Resource):
    def getJson(self):
        cs = self.settings.feeder.currentStation
        if cs is None:
            raise cyclone.web.HTTPError(404, "no current station")
        return {'station' : stationProperties(cs),
                'currentSong' : self.makeUri('currentSong')}

    def put(self):
        body = json.loads(self.request.body)
        return (self.pandoraCall('get_station_by_id', body['id'])
                .addCallback(self.settings.feeder.setStation))

    def delete(self):
        self.settings.feeder.setStation(None)

        
class CurrentSong(Resource):
    @inlineCallbacks
    def getJson(self):
        mpdSong = (yield self.mpd().currentsong())

        out = {'song' : {'mpd' : mpdCurrentSongProperties(mpdSong)}}
        try:
            ps = self.settings.feeder.pandoraSong(mpdSong['file'])
        except KeyError:
            pass
        else:
            out['song']['pandora'] = songProperties(ps)

        returnValue(out)


mapping = [(r'/', Index),
           (r'/stations/', Stations),
           (r'/stations/(\d+)(?:-[^/]+)?/', Station),
           (r'/currentStation', CurrentStation),
           (r'/currentSong', CurrentSong),
           ]
