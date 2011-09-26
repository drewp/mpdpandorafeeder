import re, time, logging
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList
from twisted.internet.threads import deferToThread

def isPandoraUrl(url):
    return re.match(r"http://audio-[^\.]+\.pandora\.com/", url)

class MpdFeeder(object):
    def __init__(self, mpdConnection):
        self.currentStation = None
        self.playedSongs = [] # Song
        self.upcomingSongs = [] # Song
        self.lastCheckTime = 0
        self.mpdConnection = mpdConnection
        self.lastError = None
        self.lastErrorTime = 0

        # this is incomplete. There should be a lock on the playlist
        # that is taken by all the methods that do writes, and
        # update's behavior should just be to skip that update (since
        # it'll get called again)
        self.updatesAllowed = True

    def moreStatus(self):
        return {
            "numPlayedSongs" : len(self.playedSongs),
            "upcomingSongBufferSize" : len(self.upcomingSongs),
            "lastErrorTime" : self.lastErrorTime,
            "lastErrorMessage" : self.lastError,
            }

    def mpd(self):
        return self.mpdConnection.currentConnection

    def setStation(self, station):
        """set to None to turn off the feeder"""
        if self.currentStation == station:
            return
        
        self.currentStation = station
        self.upcomingSongs = []
        self.playedSongs = []
        return (self.clearPandoraTailSongs()
                .addCallback(lambda _: self.startNewStation()))

    @inlineCallbacks
    def startNewStation(self):
        if self.currentStation is None:
            return

        self.updatesAllowed = False
        try:
            yield self.addNextSong()
            status = yield self.mpd().status()
            yield self.mpd().play(int(status['playlistlength'])-1)
        finally:
            self.updatesAllowed = True

    @inlineCallbacks
    def clearPandoraTailSongs(self):
        """
        clear all the upcoming pandora URLs from the end of the
        playlist, stopping at a non-pandora song or at a
        currently-playing song.

        We could just clear the ones that we know we put there, but
        that wouldn't work over a mpdpandorafeeder restart or other
        mishaps. I'm not removing pandora URLs from the *whole*
        playlist because mpdpandorafeeder claimed it would only edit
        the tail.
        """
        songs = list((yield self.mpd().playlistinfo()))
        status = (yield self.mpd().status())

        for s in reversed(songs):
            playingNow = (status['state'] == 'play' and
                          int(s['pos']) == int(status.get('song', -1)))
            if not playingNow and isPandoraUrl(s['file']):
                self.mpd().deleteid(int(s['id']))
            else:
                break

    @inlineCallbacks
    def update(self):
        if (self.mpd() is None # startup
            or self.currentStation is None # feeder is disabled
            or not self.updatesAllowed # primitive locking
            ):
            return
        
        now = time.time()
        # this time throttling is mostly to avoid load on mpd, but it
        # also helps throttle calls to pandora in case stuff goes
        # really wrong
        if now < self.lastCheckTime + 1.9:
            return
        self.lastCheckTime = now

        try:
            self.clearPlayedSongs()
            unplayed = (yield self.unplayedPandoraTailSongs())
            logging.debug("%s unplayed pandora songs" % unplayed)
            if unplayed < 1:
                yield self.addNextSong()
        except Exception, e:
            self.lastError = str(e)
            self.lastErrorTime = now
            
    @inlineCallbacks
    def unplayedPandoraTailSongs(self):
        """
        if you're not playing, the whole tail is considered unplayed
        (even if you already listened to all of it). If you skip off
        the end of the pandora music and stopped, we're not going to
        add more. You'd have to play the last one again or something.
        """
        songs = list((yield self.mpd().playlistinfo()))
        status = (yield self.mpd().status())

        unplayed = 0
        for s in reversed(songs):
            if (isPandoraUrl(s['file']) and
                int(s['pos']) > int(status.get('song', 0))):
                unplayed += 1
            else:
                break
        returnValue(unplayed)

    @inlineCallbacks
    def clearPlayedSongs(self):
        status = (yield self.mpd().status())
        if 'song' not in status:
            return

        songs = list((yield self.mpd().playlistinfo()))

        for pos in range(int(status['song']) - 1, -1, -1):
            s = songs[pos]
            if isPandoraUrl(s['file']):
                logging.info("remove played song at position %s" % pos)
                yield self.mpd().deleteid(int(s['id']))
            else:
                break

    @inlineCallbacks
    def addNextSong(self):
        if self.currentStation is None:
            return

        if not self.upcomingSongs:
            logging.info("getting more songs from pandora")
            more = (yield deferToThread(self.currentStation.get_playlist))
            self.upcomingSongs.extend(more)

        song = self.upcomingSongs.pop(0)
        self.playedSongs.append(song)
        logging.info("adding to mpd: %s %s" % (song.title, song.audioUrl))
        yield self.addStream(song.audioUrl, song.album, song.title)

    def addStream(self, url, album, title):
        return DeferredList([
            self.mpd().add(url),
            #self.mpd().sticker_put("song", url, "pandoraAlbum", album)
            #self.mpd().sticker_put("song", url, "pandoraTitle", title)
            ])

    def pandoraSong(self, url):
        for s in self.playedSongs:
            if s.audioUrl == url:
                return s
        raise KeyError()
