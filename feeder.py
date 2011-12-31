import re, time, logging
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList
from pithospandora import deferredCallWithReconnects

def isPandoraUrl(url):
    return re.match(r"http://audio-[^\.]+\.pandora\.com/", url)

class MpdFeeder(object):
    """
    call update() every few seconds
    """
    def __init__(self, pandora, mpdConnection):
        self.pandora = pandora
        self.currentStation = None
        self.playedSongs = [] # Song
        self.upcomingSongs = [] # Song
        self.lastCheckTime = 0
        self.mpdConnection = mpdConnection
        self.lastError = None
        self.lastErrorTime = 0
        self.lastStatus = "none"

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
            "lastUpdateStatus" : self.lastStatus,
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
        self.lastStatus = yield self._update()
        logging.debug("update status: %s" % self.lastStatus)

    @inlineCallbacks
    def _update(self):
        """
        returns a status string
        """
        
        if self.mpd() is None:
            returnValue("Starting up")
        if self.currentStation is None:
            returnValue("No current station")
        if not self.updatesAllowed:
            returnValue("Sending to mpd")
        
        now = time.time()
        # this time throttling is mostly to avoid load on mpd, but it
        # also helps throttle calls to pandora in case stuff goes
        # really wrong
        if now < self.lastCheckTime + 1.9:
            returnValue("Updates too fast")
        self.lastCheckTime = now

        status = ""
        try:
            status += (yield self.clearPlayedSongs())
            unplayed = (yield self.unplayedPandoraTailSongs())
            msg = "%s unplayed pandora song still on mpd playlist. " % unplayed
            logging.debug(msg)
            status += msg
            if unplayed < 1:
                status += (yield self.addNextSong())
        except Exception, e:
            self.lastError = str(e)
            self.lastErrorTime = now
            returnValue("Error: %s" % self.lastError)
        returnValue(status)

            
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

        # still trying to figure this out. If there's an undecodable
        # song, we should replace it with another from the pandora
        # queue, and not risk running out of pandora songs
        if status.get('error', '').startswith("problems decoding "):
            if 'song' not in status:
                # we could read the status message and go look for the
                # song with that url, or:
                yield self.mpd().clear()
                returnValue("Couldn't decode; cleared playlist")
            else:
                yield self.mpd().deleteid(int(status['songid']))
                returnValue("Removed a song that couldn't be decoded. ")

        if 'song' not in status:
            returnValue("Mpd isn't playing; nothing to remove. ")

        ret = ""
        songs = list((yield self.mpd().playlistinfo()))

        for pos in range(int(status['song']) - 1, -1, -1):
            s = songs[pos]
            if isPandoraUrl(s['file']):
                logging.info("remove played song at position %s" % pos)
                yield self.mpd().deleteid(int(s['id']))
                ret += "Deleted song %s. " % s['id']
            else:
                break
        returnValue(ret)

    @inlineCallbacks
    def addNextSong(self):
        if self.currentStation is None:
            returnValue("No current station; nothing to add. ")

        status = ""
        if not self.upcomingSongs:
            msg = "Getting more songs from pandora. "
            logging.info(msg)
            status += msg
            more = yield deferredCallWithReconnects(self.pandora, self.currentStation.get_playlist)
            self.upcomingSongs.extend(more)
            status += "Now we have %s. " % len(self.upcomingSongs)

        song = self.upcomingSongs.pop(0)
        self.playedSongs.append(song)
        status += "Adding a pandora song to mpd. "
        logging.info("Adding to mpd: %s %s" % (song.title, song.audioUrl))
        yield self.addStream(song.audioUrl, song.album, song.title)
        returnValue(status)
        
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
