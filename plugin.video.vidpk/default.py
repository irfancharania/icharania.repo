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
import HTMLParser
from datetime import datetime

try:
    from sqlite3 import dbapi2 as sqlite
except:
    from pysqlite2 import dbapi2 as sqlite

__plugin__ = "vidpk"
__author__ = 'Irfan Charania'
__url__ = ''
__date__ = '25-07-2013'
__version__ = '0.0.7'
__settings__ = xbmcaddon.Addon(id='plugin.video.vidpk')


def urldecode(query):
    """
    parses querystrings

    """
    d = {}
    a = query.split('&')
    for s in a:
        if '=' in s:
            k,v = map(urllib.unquote_plus, s.split('='))
            if v == 'None':
                v = None
            d[k] = v
    return d


class VidpkPlugin(object):
    cache_timeout = 60*60*4

    def connect_to_db(self):
        path = xbmc.translatePath('special://profile/addon_data/plugin.video.vidpk/')
        if not os.path.exists(path):
            os.makedirs(path)
        self.db_conn = sqlite.connect(os.path.join(path, 'bookmarks.db'))
        curs = self.db_conn.cursor()
        curs.execute("""create table if not exists bookmark_folders (
            id integer primary key,
            name text,
            parent_id integer,
            path text
        )""")

        curs.execute("""create table if not exists bookmarks (
            id integer primary key,
            name text,
            folder_id integer,
            plugin_url text
        )""")

        try:
            curs.execute("""insert into bookmark_folders (id, name, parent_id, path)
                        values (?,?,?,?)""", (1,'Bookmarks', 0, 'Bookmarks'))
        except:
            pass

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


    def get_url(self,urldata):
        """
        Constructs a URL back into the plugin with the specified arguments.

        """
        return "%s?%s" % (self.script_url, urllib.urlencode(urldata,1))


    def get_dialog(self):
        return xbmcgui.Dialog()


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


    def get_cache_dir(self):
        """
        return an acceptable cache directory.

        """
        path = xbmc.translatePath('special://profile/addon_data/plugin.video.vidpk/cache/')
        if not os.path.exists(path):
            os.makedirs(path)
        logging.debug('cache path: %s' % path)
        return path


    def get_setting(self, id):
        """
        return a user-modifiable plugin setting.

        """
        return __settings__.getSetting(id)


    def add_list_item(self, info, is_folder=True, return_only=False,
                      context_menu_items=None, clear_context_menu=False,
                      bookmark_parent=None, bookmark_id=None, bookmark_folder_id=None):
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

        if is_folder:
            if bookmark_parent is None:
                bookmark_url = self.get_url({'action': 'add_to_bookmarks', 'url': self.get_url(info)})
                context_menu_items.append(("Bookmark", "XBMC.RunPlugin(%s)" % (bookmark_url,)))
            else:
                bminfo = {'action': 'remove_from_bookmarks', 'url': self.get_url(info), 'folder_id': bookmark_parent}
                if bookmark_id is not None:
                    bminfo['bookmark_id'] = bookmark_id
                elif bookmark_folder_id is not None:
                    bminfo['bookmark_folder_id'] = bookmark_folder_id

                bookmark_url = self.get_url(bminfo)
                context_menu_items.append(("Remove From Bookmarks", "XBMC.RunPlugin(%s)" % (bookmark_url,)))

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

    def get_modal_keyboard_input(self, default=None, heading=None, hidden=False):
        keyb = xbmc.Keyboard(default, heading, hidden)
        keyb.doModal()
        val = keyb.getText()
        if keyb.isConfirmed():
            return val
        return None

    def get_existing_bookmarks(self):
        fpath = os.path.join(self.plugin.get_cache_dir(), 'vidpk.%s.categories.cache' % (self.get_cache_key(),))


    def get_resource_path(self, *path):
        """
        Returns a full path to a plugin resource.

        eg. self.get_resource_path("images", "some_image.png")

        """
        p = os.path.join(__settings__.getAddonInfo('path'), 'resources', *path)
        if os.path.exists(p):
            return p
        return ''


    def add_bookmark_folder(self):
        curs = self.db_conn.cursor()
        curs.execute("select id, name, parent_id, path from bookmark_folders order by path desc")
        rows = curs.fetchall()
        items = [r[3] for r in rows]
        dialog = self.get_dialog()
        val = dialog.select("Select a Parent for the New Folder", items)
        if val == -1:
            return None
        parent = rows[val]
        name = self.get_modal_keyboard_input('New Folder', 'Enter the name for the new folder')

        if name is None:
            return None

        newpath = parent[3]+"/"+name
        curs = self.db_conn.cursor()
        curs.execute("select * from bookmark_folders where path=?", (newpath,))
        if curs.fetchall():
            dialog.ok("Failed!", "Couldn't create folder: %s because it already exists" % (newpath,))
            return None

        curs.execute("insert into bookmark_folders (name, parent_id, path) values (?, ?, ?)", (name, parent[0], newpath))
        curs.execute("select id, name, parent_id, path from bookmark_folders where path=?", (newpath,))
        self.db_conn.commit()
        return curs.fetchall()[0]


    def action_add_to_bookmarks(self):
        curs = self.db_conn.cursor()
        curs.execute("select id, name, parent_id, path from bookmark_folders order by path asc")
        rows = curs.fetchall()
        logging.debug(rows)
        items = ["(New Folder)"]
        items += [r[3] for r in rows]
        dialog = self.get_dialog()
        val = dialog.select("Select a Bookmark Folder", items)
        logging.debug("VAL:%s" % (val,))
        if val == -1:
            return xbmcplugin.endOfDirectory(self.handle, succeeded=False)

        elif val == 0:
            folder = self.add_bookmark_folder()
            if not folder:
                return xbmcplugin.endOfDirectory(self.handle, succeeded=False)
        else:
            logging.debug("ITEMS:%s" % (items,))
            logging.debug("ROWS:%s" % (rows,))
            folder = [r for r in rows if r[3]==items[val]][0]

        bm = urldecode(self.args['url'].split("?",1)[1])
        name = self.get_modal_keyboard_input(bm['Title'], 'Bookmark Title')
        if name is None:
            return None

        curs.execute("select * from bookmarks where folder_id = ? and plugin_url = ?", (folder[0], self.args['url']))
        if curs.fetchall():
            dialog.ok("Bookmark Already Exists", "This location is already bookmarked in %s" % (folder[3],))
            return None

        curs.execute("insert into bookmarks (name, folder_id, plugin_url) values (?,?,?)", (name, folder[0], self.args['url']))
        self.db_conn.commit()

        dialog.ok("Success!", "%s has been bookmarked!" % (name,))
        return xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def action_browse_bookmarks(self):
        folder_id = int(self.args['folder_id'])
        curs = self.db_conn.cursor()
        curs.execute("select id, name, parent_id, path from bookmark_folders where parent_id = ?", (folder_id,))
        for folder in curs.fetchall():
            self.add_list_item({
                'Thumb': self.get_resource_path("images", "bookmark.png"),
                'folder_id': folder[0],
                'Title': "[%s]" % (folder[1],),
                'action': 'browse_bookmarks',
            }, bookmark_parent=folder_id, bookmark_folder_id=folder[0])

        curs.execute("select id, name, plugin_url, folder_id from bookmarks where folder_id = ?", (folder_id,))
        logging.debug("Checking For Bookmarks")
        bookmarks = curs.fetchall()
        if not bookmarks:
            self.add_list_item({'Title': '-no bookmarks-'})

        else:
            for bm in bookmarks:
                data = urldecode(bm[2].split("?", 1)[1])
                data['Title'] = bm[1]
                self.add_list_item(data, is_folder=True, bookmark_parent=bm[3], bookmark_id=bm[0])

        self.end_list(sort_methods=(xbmcplugin.SORT_METHOD_LABEL,))

    def action_remove_from_bookmarks(self):
        logging.debug("REMOVE BOOKMARK: %s" % (self.args['url'],))
        is_folder = bool(self.args.get('bookmark_folder_id', False))
        parent_id = self.args['folder_id']
        if is_folder:
            return self.remove_folder_from_bookmarks(parent_id=parent_id, folder_id=self.args['bookmark_folder_id'])
        else:
            return self.remove_bookmark_from_bookmarks(parent_id=parent_id, bookmark_id=self.args['bookmark_id'])


    def remove_folder_from_bookmarks(self, parent_id, folder_id):
        curs = self.db_conn.cursor()
        curs.execute("select id, name, parent_id, path from bookmark_folders where parent_id = ? and id = ?", (parent_id, folder_id))
        record = curs.fetchall()[0]
        dialog = self.get_dialog()
        if dialog.yesno("Are you Sure?", "Are you sure you wish to delete the bookmark folder: %s\n(All Bookmarks and Folders within it will be deleted!)" % (record[3],)):
            logging.debug("BM:Removing Bookmark Folder!")
            curs.execute("select id from bookmark_folders where path like ?", (record[3]+"%",))
            rows = curs.fetchall()
            for row in rows:
                logging.debug("deleting row: %s" % (row,))
                curs.execute("delete from bookmark_folders where id=?", row)
                curs.execute("delete from bookmarks where folder_id=?", row)
            self.db_conn.commit()
        return xbmc.executebuiltin("Container.Refresh")


    def remove_bookmark_from_bookmarks(self, parent_id, bookmark_id):
        curs = self.db_conn.cursor()
        curs.execute("select id, name, folder_id, plugin_url from bookmarks where folder_id = ? and id = ?", (parent_id, bookmark_id))
        record = curs.fetchall()[0]
        dialog = self.get_dialog()
        if dialog.yesno("Are you Sure?", "Are you sure you wish to delete the bookmark: %s" % (record[1],)):
            logging.debug("BM:Removing Bookmark!")
            curs.execute("delete from bookmarks where folder_id = ? and id = ?", (parent_id, bookmark_id))
            self.db_conn.commit()
        else:
            logging.debug("They Said No?")
        return xbmc.executebuiltin("Container.Refresh")


    def getint(self, x):
        return int(x) if x.isdigit() else None

#######################################3

    perPage = 50 # items per page

    menu = [
        ('Newest Videos', 'http://vidpk.com/rss.php' ),
        ('Featured Videos', 'http://vidpk.com/rss.php?type=featured'),
        ('Most Viewed Videos', 'http://vidpk.com/rss.php?type=views')
    ]

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

    def action_browse_episodes_xml(self):
        remote_url = self.args['remote_url']
        logging.debug('browse episodes xml: %s' % remote_url)

        data = self.fetch(remote_url, max_age=self.cache_timeout)

        tree = ET.parse(data)
        root = tree.getroot()

        episodes = root.findall('channel/item')

        img_regex = 'img src=\"(.*\.jpg)\" '
        desc_regex = '<p>(.*)</p>'

        for ep in episodes:
            data = {}
            data.update(self.args)

            tagline = ep[0].text
            link = ep[1].text
            clipid = link.split('/')[3]
            cdat = ep[2].text.strip()

            thumb = re.search(img_regex, cdat).group(1)
            desc = re.search(desc_regex, cdat).group(1)

            data['Title'] = HTMLParser.HTMLParser().unescape(tagline)
            data['Thumb'] = thumb
            data['action'] = 'play_video'
            data['clipid'] = clipid
            data['Plot'] = desc
            self.add_list_item(data, is_folder=False)
        self.end_list('episodes')


    def action_browse_episodes(self):
        currPage = int(self.args['currPage'])
        url_template = 'http://vidpk.com/ajax/getChannelVideos.php?channelid=%s&page=%s&per_page=%d'
        url = url_template % (self.args['showid'], currPage, self.perPage)

        logging.debug('browse show: %s' % url)

        page = self.fetch(url, self.cache_timeout).read()
        jdata = json.loads(page)

        #logging.debug(jdata)
        icon_template = 'http://thumb4.vidpk.com/1_%s.jpg'

        for key, val in sorted(jdata.items(), key=lambda x: self.getint(x[0])):
            if (key.isdigit()):
                data = {}
                data.update(self.args)

                clipid = val['VID']
                tagline = val['title']
                d = datetime.utcfromtimestamp(float(val['addtime']))
                yr = str(d.year)
                df = str(d.day).zfill(2) + '.' + str(d.month).zfill(2) + '.' + yr
                thumb = icon_template % clipid

                data['Title'] = HTMLParser.HTMLParser().unescape(tagline)
                data['Thumb'] = thumb
                data['action'] = 'play_video'
                data['clipid'] = clipid
                data['last_updated_pretty'] = val['last_updated']
                data['Date'] = df
                data['Year'] = yr

                self.add_list_item(data, is_folder=False)

        total = jdata['meta']['count']
        remaining = total - (currPage * self.perPage)

        if (remaining > 0):
            data['Title'] = '[B]NEXT PAGE: ' + str(currPage + 1) + ' >>[/B]'
            data['action'] = 'browse_episodes'
            data['currPage'] = currPage + 1
            self.add_list_item(data)

        self.end_list('episodes')


    def action_browse_channel(self):
        currPage = int(self.args['currPage'])
        url_template = 'http://vidpk.com/ajax/getStationChannels.php?stationid=%s&page=%d&per_page=%d'
        url = url_template % (self.args['entry_id'], currPage, self.perPage)
        logging.debug('browse channel: %s' % url)

        page = self.fetch(url, self.cache_timeout).read()
        jdata = json.loads(page)

        #logging.debug(jdata)

        icon_template = 'http://vidpk.com/images/channels/%s.jpg'

        for key, val in sorted(jdata.items(), key=lambda x: self.getint(x[0])):
            if (key.isdigit()):
                data = {}
                data.update(self.args)

                showid = val['CHID']
                tagline = val['name']
                d = val['lastupdated']
                df = d[8:10] + '.' + d[5:7] + '.' + d[0:4]

                thumb = self.get_resource_path('images', showid + '.jpg')
                if len(thumb) == 0:
                    thumb = icon_template % showid

                data['Title'] = HTMLParser.HTMLParser().unescape(tagline)
                data['Thumb'] = thumb
                data['action'] = 'browse_episodes'
                data['showid'] = showid
                data['last_updated_pretty'] = val['last_updated']
                data['Date'] = df
                self.add_list_item(data)

        # handle meta
        total = jdata['meta']['count']
        remaining = total - (currPage * self.perPage)

        if (remaining > 0):
            # next page
            data['Title'] = '[B]NEXT PAGE: ' + str(currPage + 1) + ' >>[/B]'
            data['action'] = 'browse_channel'
            data['currPage'] = currPage + 1
            self.add_list_item(data)

        self.end_list()

    def action_get_channels(self):
        for ch, id in self.channels:
            thumb = 'http://vidpk.com/images/stations/%s.png' % id
            self.add_list_item({
                'Title': ch,
                'action': 'browse_channel',
                'Thumb': thumb,
                'entry_id': id,
                'currPage': 1
            })
        self.end_list('movies', [xbmcplugin.SORT_METHOD_LABEL])

    def action_plugin_root(self):
        self.add_list_item({
            'Title': '[B]Bookmarks[/B]',
            'action': 'browse_bookmarks',
            'folder_id': 1
        }, bookmark_parent=0)

        for desc, link in self.menu:
            self.add_list_item({
                'Title': desc,
                'action': 'browse_episodes_xml',
                'remote_url': link
            })

        self.add_list_item({
            'Title': 'Browse Channels',
            'action': 'get_channels'
        })

        self.end_list()

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


    def check_cache(self):
        cachedir = self.get_cache_dir()
        version_file = os.path.join(cachedir, 'version.' + __version__)
        if not os.path.exists(version_file):
            shutil.rmtree(cachedir)
            os.mkdir(cachedir)
            f = open(os.path.join(cachedir,'version.' + __version__), 'w')
            f.write("\n")
            f.close()

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
        self.connect_to_db()
        self.check_cache()
        logging.debug("Constructed Plugin %s" % (self.__dict__,))


if __name__ == '__main__':
    plugin = VidpkPlugin(*sys.argv)
    plugin()