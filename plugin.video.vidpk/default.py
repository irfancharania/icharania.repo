import os, sys
import shutil
import sha
import cgi
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import logging
logging.basicConfig(level=logging.DEBUG)
import urllib, urllib2, urlparse, re, string, xml.etree.ElementTree as ET
import time
import simplejson as json
from utils import urldecode

try:
    from sqlite3 import dbapi2 as sqlite
except:
    from pysqlite2 import dbapi2 as sqlite

__plugin__ = "vidpk"
__author__ = 'Irfan Charania'
__url__ = ''
__date__ = '07-07-2013'
__version__ = '0.0.1'
__settings__ = xbmcaddon.Addon(id='plugin.video.vidpk')



class VidpkPlugin(object):
    cache_timeout = 60*60*4

    def _urlopen(self, url, retry_limit=4):
        retries = 0
        while retries < retry_limit:
            logging.debug("fetching %s" % (url,))
            url_scheme, netloc, path, query, fragment = urlparse.urlsplit(url)
            req = urllib2.Request(url)
            req.add_header("Referer", "%s://%s/" % (url_scheme, netloc))
            try:
                return urllib2.urlopen(req)
            except (urllib2.HTTPError, urllib2.URLError), e:
                retries += 1
            raise Exception("Failed to retrieve page: %s" %(url,))

    def _urlretrieve(self, url, filename, retry_limit=4):
        retries = 0
        while retries < retry_limit:
            logging.debug("fetching %s" % (url,))
            try:
                return urllib.urlretrieve(url, filename)
            except (urllib.HTTPError, urllib.URLError), e:
                retries += 1
            raise Exception("Failed to retrieve page: %s" %(url,))

    def fetch(self, url, max_age=None):
        if max_age is None:
            return self._urlopen(url)

        tmpurl = url
        scheme, tmpurl = tmpurl.split("://",1)
        netloc, path = tmpurl.split("/",1)
        fname = sha.new(path).hexdigest()
        _dir = fname[:4]
        cacheroot = self.get_cache_dir()
        cachepath = os.path.join(cacheroot, netloc, _dir)
        if not os.path.exists(cachepath):
            os.makedirs(cachepath)

        download = True
        cfname = os.path.join(cachepath, fname)
        if os.path.exists(cfname):
            ctime = os.path.getctime(cfname)
            if time.time() - ctime < max_age:
                download = False

        if download:
            logging.debug("Fetching: %s" % (url,))
            urllib.urlretrieve(url, cfname)
        else:
            logging.debug("Using Cached: %s" % (url,))

        return open(cfname)


    def get_cache_dir(self):
        """
        return an acceptable cache directory.

        """
        path = xbmc.translatePath('special://profile/addon_data/plugin.video.vidpk/cache/')
        if not os.path.exists(path):
            os.makedirs(path)
        logging.debug('cache path: %s' % path)
        return path


    def get_url(self,urldata):
        """
        Constructs a URL back into the plugin with the specified arguments.

        """
        return "%s?%s" % (self.script_url, urllib.urlencode(urldata,1))

    def set_stream_url(self, url, info=None):
        """
        Resolve a Stream URL and return it to XBMC.

        'info' is used to construct the 'now playing' information
        via add_list_item.

        """
        listitem = xbmcgui.ListItem(label='clip', path=url)
        xbmcplugin.setResolvedUrl(self.handle, True, listitem)


    def end_list(self, content='movies', sort_methods=None):
        xbmcplugin.setContent(self.handle, content)
        if sort_methods is None:
            sort_methods = (xbmcplugin.SORT_METHOD_NONE,)

        for sm in sort_methods:
            xbmcplugin.addSortMethod(self.handle, sm)
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)


    def get_setting(self, id):
        """
        return a user-modifiable plugin setting.

        """
        return __settings__.getSetting(id)


    def add_list_item(self, info, is_folder=True, return_only=False,
                      context_menu_items=None, clear_context_menu=False):
        """
        Creates an XBMC ListItem from the data contained in the info dict.

        if is_folder is True (The default) the item is a regular folder item

        if is_folder is False, the item will be considered playable by xbmc
        and is expected to return a call to set_stream_url to begin playback.

        if return_only is True, the item item isn't added to the xbmc screen but
        is returned instead.


        Note: This function does some renaming of specific keys in the info dict.
        you'll have to read the source to see what is expected of a listitem, but in
        general you want to pass in self.args + a new 'action' and a new 'remote_url'
        'Title' is also required, anything *should* be optional

        """
        if context_menu_items is None:
            context_menu_items = []

        info.setdefault('Thumb', '')
        info.setdefault('Icon', info['Thumb'])
        if 'Rating' in info:
            del info['Rating']

        li=xbmcgui.ListItem(
            label=info['Title'],
            iconImage=info['Icon'],
            thumbnailImage=info['Thumb']
        )

        if not is_folder:
            li.setProperty("IsPlayable", "true")
            context_menu_items.append(("Queue Item", "Action(Queue)"))

        li.setInfo(type='Video', infoLabels=dict((k, unicode(v)) for k, v in info.iteritems()))

        # Add Context Menu Items
        if context_menu_items:
            li.addContextMenuItems(context_menu_items,
                                   replaceItems=clear_context_menu)


        # Handle the return-early case
        if not return_only:
            kwargs = dict(
                handle=self.handle,
                url=self.get_url(info),
                listitem=li,
                isFolder=is_folder
            )
            return xbmcplugin.addDirectoryItem(**kwargs)

        return li

#######################################3

    channels = [
        ('Geo', '1'),
        ('Hum TV', '2'),
        ('Aaj TV', '3'),
        ('ARY Digital', '4'),
        ('ATV', '5'),
        ('Express Entertainment', '6'),
        ('Indus', '7'),
        ('PTV', '8'),
        ('TV One', '9'),
        ('Urdu 1', '10'),
        ('Masala TV', '11'),
        ('Khyber TV', '12'),
        ('ARY Zauq', '13'),
        ('Zaiqa TV', '14'),
        ('Dunya TV', '15'),
        ('CNBC', '17'),
        ('A Plus', '18'),
        ('Dawn News', '19'),
        ('Geo News', '20'),
        ('ARY Musik', '21'),
        ('Express News', '22'),
        ('ARY News', '23'),
        ('Aag TV', '24'),
        ('Samaa TV', '25'),
        ('Oxygene', '26'),
        ('Afghan TV', '27'),
        ('Geo Kahani', '28')
    ]

    def action_play_video(self):
        url_template = 'http://vidpk.com/playlist.php?v=%s'
        remote_url = url_template % (self.args['clipid'])

        logging.debug(remote_url)

        data = self.fetch(remote_url, max_age=self.cache_timeout)

        tree = ET.parse(data)
        root = tree.getroot()

        namespace = "{http://xspf.org/ns/0/}"
        e = root.findall('{0}trackList/{0}track/{0}location'.format(namespace))
        url = e[1].text

        logging.debug(url)

        url = url + '|referer=http://vidpk.com/jwplayer/jwplayer.flash.swf'

        return self.set_stream_url(url)

    def action_browse_episodes(self):
        url_template = 'http://vidpk.com/ajax/getChannelVideos.php?channelid=%s&page=%s'
        url = url_template % (self.args['showid'], '1')

        #logging.debug('browse show: %s' % url)

        data = self.fetch(url, self.cache_timeout).read()
        jdata = json.loads(data)

        #logging.debug(jdata)

        icon_template = 'http://thumb4.vidpk.com/1_%s.jpg'

        for episode in sorted(jdata):
            if (episode == 'meta'):
                continue;

            thumb = icon_template % jdata[episode]['VID']

            data = {}
            data.update(self.args)
            data['Title'] = jdata[episode]['title']
            data['Thumb'] = thumb
            data['action'] = 'play_video'
            data['clipid'] = jdata[episode]['VID']
            data['last_updated_pretty'] = jdata[episode]['last_updated']
            data['last_updated'] = jdata[episode]['addtime']
            self.add_list_item(data, is_folder=False)
        self.end_list('episodes')


    def action_browse_channel(self):
        url_template = 'http://vidpk.com/ajax/getStationChannels.php?stationid=%s&page=%s&per_page=%s'
        url = url_template % (self.args['entry_id'], '1', '10')
        #logging.debug('browse channel: %s' % url)

        data = self.fetch(url, self.cache_timeout).read()
        jdata = json.loads(data)

        #logging.debug(jdata)

        icon_template = 'http://vidpk.com/images/channels/%s.jpg'

        for show in jdata:
            if (show == 'meta'):
                continue;

            thumb = icon_template % jdata[show]['CHID']

            data = {}
            data.update(self.args)
            data['Title'] = jdata[show]['name']
            data['Thumb'] = thumb
            data['action'] = 'browse_episodes'
            data['showid'] = jdata[show]['CHID']
            data['last_updated_pretty'] = jdata[show]['last_updated']
            data['last_updated'] = jdata[show]['lastupdated']
            self.add_list_item(data)
        self.end_list()


    def action_plugin_root(self):
        for ch, id in self.channels:
            self.add_list_item({
                'Title': ch,
                'action': 'browse_channel',
                'entry_id': id
            })
        self.end_list('movies', [xbmcplugin.SORT_METHOD_LABEL])

    def __call__(self):
        """
        This is the main entry point of the plugin.
        the querystring has already been parsed into self.args

        """
        action = self.args.get('action', None)
        if not hasattr(self, 'action_%s' % (action,)):
            action = 'plugin_root'

        action_method = getattr(self, 'action_%s' % (action, ))
        return action_method()


    def __init__(self, script_url, handle, querystring):
        self.script_url = script_url
        self.handle = int(handle)
        if len(querystring) > 2:
            self.querystring = querystring[1:]
            items = urldecode(self.querystring)
            self.args = dict(items)
        else:
            self.querystring = querystring
            self.args = {}
        #self.connect_to_db()
        #self.check_cache()
        logging.debug("Constructed Plugin %s" % (self.__dict__,))


if __name__ == '__main__':
    plugin = VidpkPlugin(*sys.argv)
    plugin()
