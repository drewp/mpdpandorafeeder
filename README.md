mpdpandorafeeder
================

web service that feeds mpd with streaming music from pandora. The only
time it controls the mpd transport is when you change stations.

Setup
-----

*  Have pithos installed, and run it to setup your pandora account. This
   service reads the pithos config files.

*  easy_install python-mpd-twisted
  
*  easy_install cyclone

Usage
-----

    python mpdpandorafeeder.py --mpd localhost:6600 --port 9999
    curl http://localhost:9999/stations/
    curl -XPUT http://localhost:9999/currentStation -d '{ ..one of the station representations.. }'
    curl http://localhost:9999/currentSong
    curl -XDELETE http://localhost:9999/currentStation


Effect on playlist
------------------

This service tries to cooperate with other mpd playlist management you
might do. It appends its songs to the end of the list, and it aborts
if it sees a non-pandora song at the end. This means you can be
playing a local song and then have the next one be a pandora song, or
you can be playing a pandora and transition back to local songs. How
many pandora songs will be at the end of your playlist:

    0: if you haven't set a currentStation, or after you delete currentStation
    1: only very briefly
    2: during normal playback (so you can skip the current song)

Internal state
--------------

This service stores in memory the current station choice and a buffer
of the upcoming pandora song picks. For robustness, it uses your live
mpd playlist to determine what pandora songs are at the end of the
playlist.

Resources (but it's REST, so you only have to know how to find the root one)
----------------------------------------------------------------------------

    GET /
      current status and links to /stations and /currentStation

    GET /stations/
      List of stations with links

    GET /stations/<id>/
      Description of a station. For clarity, you can append a dash and
      more letters to the id and they will be ignored. E.g. /stations/123/
      can be accessed as /stations/123-favoriteSongs/
      
    PUT /currentStation
      Body is a station representation you got previously.
      
      Make this station be the one we're feeding to mpd. If this is a new
      station than the last one you requested (including if
      mpdpandorafeeder restarts and forgets the last one you requestd),
      all pandora songs at the end of your mpd playlist will be cleared,
      and we'll tell mpd to play the first new one we add. (If there was
      an option to disable some of this behavior, you would be able to
      change-station-after-the-current-song which might be cool.)

    GET /currentStation
      Station representation that you PUT before, and a link to /currentSong.

    DELETE /currentStation

      Stop feeding this station to mpd. This immediately removes the
      upcoming songs, but doesn't stop playback or remove the playing
      song. This puts you in a good position to add a local song after the
      currently-playing pandora song.

    GET /currentSong

      This returns mpd information about the current song (pandora or
      not), augmented with pandora details if the song is on there because
      of the current station. Notable attributes:

        {song: {mpd: {...}
                pandora: {"album": "...", "albumDetailURL": "http://...",
                          "artRadio": "http://...jpg", "artist": "...",
                          "title": "...", "songDetailURL": "http://...",
                          "fileGain": "-1.3", ...}
