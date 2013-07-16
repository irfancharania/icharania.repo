import os, sys
import shutil
import sha
import cgi
import xbmc, xbmcaddon, xbmcgui, xbmcplugin
import requests, urlresolver
from BeautifulSoup import BeautifulSoup
import logging
logging.basicConfig(level=logging.DEBUG)
import urllib, urllib2, urlparse, re, string
import time
import HTMLParser
from datetime import datetime

try:
    import StorageServer
except:
    import storageserverdummy as StorageServer
cache = StorageServer.StorageServer('plugin.video.paktv', 6)

try:
    from sqlite3 import dbapi2 as sqlite
except:
    from pysqlite2 import dbapi2 as sqlite


__plugin__ = "paktv"
__author__ = 'Irfan Charania'
__url__ = ''
__date__ = '14-07-2013'
__version__ = '0.0.2'
__settings__ = xbmcaddon.Addon(id='plugin.video.paktv')


# allows us to get mobile version
user_agent = 'Mozilla/5.0 (iPhone; U; CPU iPhone OS 4_2_1 like Mac OS X; en-us) AppleWebKit/533.17.9 (KHTML, like Gecko) Version/5.0.2 Mobile/8G4 Safari/6533.18.5'


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


class PaktvPlugin(object):

    def connect_to_db(self):
        path = xbmc.translatePath('special://profile/addon_data/plugin.video.paktv/')
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
#
#   def _urlopen(self, url, retry_limit=4):
#       retries = 0
#       while retries < retry_limit:
#           logging.debug("fetching %s" % (url,))
#           url_scheme, netloc, path, query, fragment = urlparse.urlsplit(url)
#           req = urllib2.Request(url)
#           req.add_header("Referer", "%s://%s/" % (url_scheme, netloc))
#           try:
#               return urllib2.urlopen(req)
#           except (urllib2.HTTPError, urllib2.URLError), e:
#               retries += 1
#           raise Exception("Failed to retrieve page: %s" %(url,))
#
#   def _urlretrieve(self, url, filename, retry_limit=4):
#       retries = 0
#       while retries < retry_limit:
#           logging.debug("fetching %s" % (url,))
#           try:
#               return urllib.urlretrieve(url, filename)
#           except (urllib.HTTPError, urllib.URLError), e:
#               retries += 1
#           raise Exception("Failed to retrieve page: %s" %(url,))
#

    def get_url(self,urldata):
        """
        Constructs a URL back into the plugin with the specified arguments.

        """
        return "%s?%s" % (self.script_url, urllib.urlencode(urldata,1))

#
#    def get_dialog(self):
#        return xbmcgui.Dialog()
#

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
        fpath = os.path.join(self.plugin.get_cache_dir(), 'paktv.%s.categories.cache' % (self.get_cache_key(),))


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

#######################################

    base_url = 'http://www.thepaktv.me/forums/'
    section_url_template = 'forumdisplay.php?f=%s'

    # supported by url resolver module
    resolvable_sites = [
        ('tube.php', 'Youtube', 'youtube.com'),
        #('daily.php', 'Daily Motion', 'dailymotion.com'),
        #('hb.php', 'Hosting Bulk', 'hostingbulk.com'),
        #('tune.php', 'Tune PK', 'tune.pk'),
        #('vw.php', 'Video Weed', 'videoweed.es'),
    ]

    frame_menu = [
        ('Ramdan Kareem Programs', 'http://www.paktvnetwork.com/Ads/forum/update3/Today/ramadan.html' ),
        ('Today\'s Top Dramas', 'http://www.paktvnetwork.com/Ads/forum/update3/Today/6.html'),
        ('Today\'s Talk Shows', 'http://www.paktvnetwork.com/Ads/forum/update3/Shows/5.html'),
        ('Morning Shows', 'http://www.paktvnetwork.com/Ads/forum/update3/MorningShows.html'),
        ('Hit Dramas', 'http://www.paktvnetwork.com/Ads/forum/update3/HitDramas.html'),
        ('New Arrivals', 'http://www.paktvnetwork.com/Ads/forum/update3/newdramas.html'),
    ]

    drama_channel_menu = [
        ('Geo', '16'),
        ('ARY Digital', '18'),
        ('Hum TV', '17'),
        ('PTV Home', '15'),
        ('Urdu 1', '954'),
        ('Geo Kahani', '1118'),
        ('A Plus', '24'),
        ('TV One', '19'),
        ('Express Entertainment', '619'),
        ('ARY Musik', '25'),
    ]

###########################################
    def get_url_data(self, url):
        logging.debug("Fetching: %s" % (url,))

        headers = { 'User-Agent': user_agent }
        r = requests.get(url, headers=headers)
        return r.content

    def fetch(self, url):
        return cache.cacheFunction(self.get_url_data, url)

############################################

    def action_play_video(self):
        remote_url = self.args['remote_url']
        vid = self.args['vid']
        logging.debug('play video: %s - %s' % (remote_url, vid))

        hmf = urlresolver.HostedMediaFile(host=remote_url, media_id=vid)
        if hmf:
            url = hmf.resolve()

        else:
            raise Exception('unable to play')

        return self.set_stream_url(url)


    def action_get_episode(self):
        remote_url = self.args['remote_url']
        logging.debug('browse episode: %s' % remote_url)

        data = self.fetch(remote_url)
        soup = BeautifulSoup(data)

        linklist = soup.find('ol', id='posts').find('blockquote', "postcontent restore").findAll('a')

        for l in linklist:
            href = l['href']

            for txt, desc, lnk in self.resolvable_sites:
                if (href.find(txt) > 0): # match resolvable site

                    v = href.find('v=')
                    if (v > 0):
                        vid = href[v+2:]
                        tagline = '[B]' + desc + '[/B]: ' + l.text

                        data = {}
                        data.update(self.args)

                        data['Title'] = HTMLParser.HTMLParser().unescape(tagline)
                        data['action'] = 'play_video'
                        data['remote_url'] = lnk
                        data['vid'] = vid

                        self.add_list_item(data, is_folder=False)
                    break;

        self.end_list()


    def action_browse_episodes(self):
        remote_url = self.args['remote_url']
        logging.debug('browse show: %s' % remote_url)

        data = self.fetch(remote_url)
        soup = BeautifulSoup(data)

        linklist = soup.find('ul', id='threads').findAll('h3')

        for l in linklist:
            data = {}
            data.update(self.args)

            tagline = l.a.text
            link = l.a['href']

            data['Title'] = HTMLParser.HTMLParser().unescape(tagline)
            data['action'] = 'get_episode'
            data['remote_url'] = self.base_url + link
            self.add_list_item(data)
        self.end_list()


    def action_browse_shows(self):
        remote_url = self.args['remote_url']
        logging.debug('browse show: %s' % remote_url)

        data = self.fetch(remote_url)
        soup = BeautifulSoup(data)

        sub = soup.find('ul', attrs={'data-role': 'listview', 'data-theme': 'd', 'class': 'forumbits'})
        h = sub.findAll('li')
        linklist = [x for x in h if x.has_key('id')]

        for l in linklist:
            data = {}
            data.update(self.args)

            tagline = HTMLParser.HTMLParser().unescape(l.a.text)
            link = l.a['href']


            if l.a.span:
                action = 'browse_shows'
                tagline = '[B]' + tagline + '[/B]'
            else:
                action = 'browse_episodes'

            data['Title'] = tagline
            data['action'] = action
            data['remote_url'] = self.base_url + link
            self.add_list_item(data)
        self.end_list()


    def action_browse_frames(self):
        remote_url = self.args['remote_url']
        logging.debug('browse frame: %s' % remote_url)

        data = self.fetch(remote_url)
        soup = BeautifulSoup(data)

        linklist = soup.findAll('a')

        for l in linklist:
            data = {}
            data.update(self.args)

            tagline = l.text
            link = l['href']

            data['Title'] = HTMLParser.HTMLParser().unescape(tagline)
            data['action'] = 'browse_episodes'
            data['remote_url'] = link
            self.add_list_item(data)
        self.end_list(sort_methods=(xbmcplugin.SORT_METHOD_LABEL,))


    def action_get_drama_channel_menu(self):
        for desc, link in self.drama_channel_menu:
            self.add_list_item({
                'Title': desc,
                'action': 'browse_shows',
                'remote_url': self.base_url + (self.section_url_template % link)
            })
        self.end_list(sort_methods=(xbmcplugin.SORT_METHOD_LABEL,))


    def action_plugin_root(self):
        #self.add_list_item({
        #    'Title': '[B]Bookmarks[/B]',
        #    'action': 'browse_bookmarks',
        #    'folder_id': 1
        #}, bookmark_parent=0)

        for desc, link in self.frame_menu:
            self.add_list_item({
                'Title': desc,
                'action': 'browse_frames',
                'remote_url': link
            })

        self.add_list_item({
            'Title': '[B]Browse Pakistani Dramas[/B]',
            'action': 'get_drama_channel_menu'
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
        logging.debug("Constructed Plugin %s" % (self.__dict__,))


if __name__ == '__main__':
    plugin = PaktvPlugin(*sys.argv)
    plugin()