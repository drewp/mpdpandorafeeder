
import logging
import pithos.pithosconfig 
import pithos.pandora
from pithos.PreferencesPithosDialog import PreferencesPithosDialog

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
    pandora.connect(pref['username'], pref['password'])
    logging.info("Pandora connected. Pithos version %s" %
                 pithos.pithosconfig.VERSION)

    return pandora
