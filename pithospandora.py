
import logging, os
import pithos.pithosconfig 
import pithos.pandora
from pithos.PreferencesPithosDialog import PreferencesPithosDialog
from twisted.internet.threads import deferToThread
from pithos.pandora import PandoraAuthTokenInvalid

class GetPref(PreferencesPithosDialog):
    def just_get_prefs(self):
        getattr(self, '_PreferencesPithosDialog__load_preferences')()
        return self.get_preferences()
        
    def setup_fields(self):
        pass

def newPandora():
    """
    this is blocking
    """
    gp = GetPref()
    pref = gp.just_get_prefs()

    pandora = pithos.pandora.make_pandora()
    pandora.set_proxy(pref['proxy'])
    pandora.set_audio_format(pref['audio_format'])

    def reconnect():
        logging.warn("reconnecting")
        return pandora.connect(pref['username'], pref['password'])
    pandora.mpdpandorafeeder_reconnect = reconnect

    pandora.mpdpandorafeeder_reconnect()

    logging.info("Pandora connected. Pithos version %s" %
                 pithos.pithosconfig.VERSION)

    return pandora

def deferredCallWithReconnects(pandora, c, *args):
    """
    run a blocking pandora call in a thread, and also reconnect the
    pandora session if it has timed out

    """
    def eb(f):
        logging.warn("eb %r", f)
        f.trap(PandoraAuthTokenInvalid)
        logging.warn("PandoraAuthTokenInvalid")
        if c.__name__ == 'mpdpandorafeeder_reconnect':
            logging.error("reconnect is failing")
            os.abort()
        return (
            deferredCallWithReconnects(pandora,
                                       pandora.mpdpandorafeeder_reconnect)
            .addCallback(deferredCallWithReconnects, pandora, c, *args))
    print "deferToThread(%r,%r) pandora=%r" % (c, args, pandora)
    return deferToThread(c, *args).addErrback(eb)
