import os
import sys
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import requests
import urlresolver
from BeautifulSoup import BeautifulSoup
import logging
logging.basicConfig(level=logging.DEBUG)
import urllib
import re
import HTMLParser

try:
    import cPickle as pickle
except:
    import pickle

try:
    import StorageServer
except:
    import storageserverdummy as StorageServer
cache = StorageServer.StorageServer('plugin.video.paktv', 6)

try:
    from sqlite3 import dbapi2 as sqlite
except:
    from pysqlite2 import dbapi2 as sqlite

try:
    from addon.common.addon import Addon
except:
    from t0mm0.common.addon import Addon
addon = Addon('plugin.video.paktv', argv=sys.argv)

__plugin__ = "paktv"
__author__ = 'Irfan Charania'
__url__ = ''
__date__ = '18-08-2013'
__version__ = '0.1.2'
__settings__ = xbmcaddon.Addon(id='plugin.video.paktv')


# allows us to get mobile version
user_agent = 'Mozilla/5.0 (Linux; U; Android 4.0.4; en-gb; GT-I9300 Build/IMM76D) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30'

# supported by url resolver module
# match, title, host, setting id
resolvable_sites = [
    ('tube.php', '[COLOR white]Youtube[/COLOR]', 'youtube.com'),
    ('daily.php', '[COLOR orange]Daily Motion[/COLOR]', 'dailymotion.com'),
    ('hb.php', '[COLOR red]Hosting Bulk[/COLOR]', 'hostingbulk.com'),
    ('hostingbulk.php', '[COLOR red]Hosting Bulk[/COLOR]', 'hostingbulk.com'),
    ('tune.php', '[COLOR green]Tune PK[/COLOR]', 'tune.pk'),
    ('vw.php', '[COLOR yellow]Video Weed[/COLOR]', 'videoweed.es'),
    ('fb.php', '[COLOR blue]Facebook[/COLOR]', 'facebook.com'),
    ('nowvideo.php', '[COLOR grey2]Now Video[/COLOR]', 'nowvideo.eu'),
    ('put.php', '[COLOR grey]Putlocker[/COLOR]', 'putlocker.com'),
]


def urldecode(query):
    """
    parses querystrings

    """
    d = {}
    a = query.split('&')
    for s in a:
        if '=' in s:
            k, v = map(urllib.unquote_plus, s.split('='))
            if v == 'None':
                v = None
            d[k] = v
    return d


class PaktvPlugin(object):

    def connect_to_db(self):
        path = xbmc.translatePath(
            'special://profile/addon_data/plugin.video.paktv/')
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
            curs.execute(
                """insert into bookmark_folders (id, name, parent_id, path)
                values (?,?,?,?)""", (1,'Bookmarks', 0, 'Bookmarks'))
        except:
            pass

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
    section_url_template = 'forumdisplay.php?f='

    frame_menu = [
        ('Today\'s Top Dramas', 'http://www.paktvnetwork.com/Ads/forum/update3/Today/6.html'),
        ('Today\'s Talk Shows', 'http://www.paktvnetwork.com/Ads/forum/update3/Shows/5.html'),
        ('Morning Shows', 'http://www.paktvnetwork.com/Ads/forum/update3/MorningShows.html'),
        ('Hit Dramas', 'http://www.paktvnetwork.com/Ads/forum/update3/HitDramas.html'),
        ('New Arrivals', 'http://www.paktvnetwork.com/Ads/forum/update3/newdramas.html'),
        ('Ramdan Kareem Programs', 'http://www.paktvnetwork.com/Ads/forum/update3/Today/ramadan.html' ),
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
        ('ATV', '23'),
    ]

    morning_shows_menu = [
        ('Morning Shows', '286'),
        ('Cooking Shows', '141'),
    ]

    news_shows_menu = [
        ('Geo News', '26'),
        ('Express News', '27'),
        ('Dunya TV', '29'),
        ('AAJ News', '28'),
        ('Dawn News', '53'),
        ('Ary News', '30'),
        ('CNBC Pak', '735'),
        ('Sama News', '31'),
    ]

    ramzan_shows_menu = [
        ('Ramzan TV Shows', '375'),
        ('Ramzan Cooking Shows', '376'),
        ('Ramzan Special Dramas & Telefilms', '400')
    ]

###########################################
    def get_url_data(self, url):
        logging.debug("Fetching: %s" % (url,))

        headers = { 'User-Agent': user_agent }
        r = requests.get(url, headers=headers)
        return r.content

    def fetch(self, url):
        return cache.cacheFunction(self.get_url_data, url)

    def get_available_hosts(self):
        return resolvable_sites

############################################

    def add_stream_to_playlist(self, media, playlist):
        if media:
            stream_url = media.resolve()
            if stream_url:
                playlist.add(stream_url)
                logging.debug('adding stream to playlist: %s' % stream_url)


    def action_play_video_continuous(self):
        dic = self.args['media']
        byhostdic = pickle.loads(dic)

        source = urlresolver.choose_source([x[1][0] for x in byhostdic.items()])
        if source:
            host = source.get_host()
            logging.debug('play from host: %s' % host)

            playlist = xbmc.PlayList(1)
            playlist.clear()

            # add to playlist
            map(lambda x: self.add_stream_to_playlist(x, playlist), byhostdic[host])

            xbmc.Player().play(playlist)


    def action_play_video(self):
        media = self.args['media']
        dl = pickle.loads(media)

        source = urlresolver.choose_source(dl)
        if source:
            stream_url = source.resolve()
        else:
            stream_url = False

        logging.debug('play episode: %s' % stream_url)
        #Play the stream
        if stream_url:
            addon.resolve_url(stream_url)
        else:
            addon.show_error_dialog(["[B][COLOR red]Unable to play video[/COLOR][/B]", "Please choose another source"])
            return



    # There are a lot of mal-formed links
    # e.g. <a href='link1'>part of </a><a href='link1'>title</a>
    # This method will merge them into a unique dictionary
    def get_clean_dictionary(self, ol):
        tdic = {}
        ah = self.get_available_hosts()

        for li in ol:
            key = li['href']
            value = li.text
            if value:
                for txt, desc, host in ah:
                    # has description & match resolvable site
                    if (key.find(txt) > 0):
                        if not (key in tdic):
                            v = key.find('v=')
                            if (v > 0): vid = key[v+2:]
                            if len(vid) > 0:
                                arr = [value, host, vid]
                                tdic[key] = arr
                        else:
                            tdic[key][0] = tdic[key][0] + ' ' + value

                        break
        return tdic


    # This has turned into a mess...
    def action_get_episode(self):
        remote_url = self.args['remote_url']
        logging.debug('get episode: %s' % remote_url)

        data = self.fetch(remote_url)
        soup = BeautifulSoup(data)

        linklist = soup.find('ol', id='posts').find('blockquote', "postcontent restore").findAll('a')

        # clean up bad tags
        tdic = self.get_clean_dictionary(linklist)


        if len(tdic) > 0:
            bypartdic = {}
            byhostdic = {}

            for __, item in tdic.items():
                partnum = re.compile('[pP]art\s*(\d+)').findall(item[0])
                if partnum and len(partnum) > 0:
                    part = 'Part {partnum}'.format(partnum=partnum[0])
                    host = item[1]
                    vid = item[2]
                    #title = "[B]{host}[/B] ::: {part}".format(host=host, part=part)
                    title = "[B]{host}[/B]".format(host=host)
                else:
                    ''' assume it is a single link '''
                    part = 'Single link'
                    host = item[1]
                    vid = item[2]
                    title = "[B]{host}[/B]".format(host=host)

                if part:
                    media = urlresolver.HostedMediaFile(host=host,
                                                        media_id=vid,
                                                        title=title)

                    if len(media.get_url()) > 0:
                        if not (part in bypartdic):
                            bypartdic[part] = [media]
                        else:
                            bypartdic[part].append(media)

            if len(bypartdic) > 0:
                for key, value in bypartdic.items():
                    self.add_list_item({
                        'Title': key,
                        'action': 'play_video',
                        'media': pickle.dumps(value)
                    }, is_folder=False)

                # do not offer continuous play if only 1 part
                # and if there is a single link available
                if ((not 'Single link' in bypartdic) and
                        (len(bypartdic) > 1)):

                    # Add sorted parts by host
                    for part, medialist in sorted(bypartdic.items()):
                        for media in medialist:
                            host = media.get_host()
                            byhostdic.setdefault(host, []).append(media)

                    self.add_list_item({
                        'Title': 'Continuous Play (EXPERIMENTAL)',
                        'action': 'play_video_continuous',
                        'media': pickle.dumps(byhostdic)
                    }, is_folder=False)


                self.end_list(sort_methods=(xbmcplugin.SORT_METHOD_LABEL,))
            else:
                addon.show_error_dialog(['[B][COLOR red]No episodes found in your enabled hosts.[/COLOR][/B]',
                    'Please check urlresolver settings'])
                return
        else:
            addon.show_error_dialog(['[B][COLOR red]No episodes found.[/COLOR][/B]'])
            return

    def action_browse_episodes(self):
        remote_url = self.args['remote_url']
        logging.debug('browse episode: %s' % remote_url)

        if ('current_page' in self.args):
            current_page = int(self.args['current_page'])
        else:
            current_page = 1

        data = self.fetch(remote_url)
        soup = BeautifulSoup(data)

        container = soup.find('ul', id='threads')
        if container and len(container) > 0:
            linklist = container.findAll('h3')

            for l in linklist:
                data = {}
                data.update(self.args)

                tagline = l.a.text
                link = l.a['href']

                data['Title'] = HTMLParser.HTMLParser().unescape(tagline)
                data['action'] = 'get_episode'
                data['remote_url'] = self.base_url + link
                self.add_list_item(data)

            navlink = soup.find('div', attrs={'data-role': 'vbpagenav'})
            if navlink:
                total_pages = int(navlink['data-totalpages'])
                if (total_pages and total_pages > current_page):
                    pg = remote_url.find('&page=')
                    url = remote_url[:pg] if pg > 0 else remote_url

                    data['Title'] = '[B]>>> Next Page: (%d of %d)[/B]' % (current_page + 1, total_pages)
                    data['action'] = 'browse_episodes'
                    data['remote_url'] = url + '&page=' + str(current_page + 1)
                    data['current_page'] = str(current_page + 1)
                    self.add_list_item(data)

            self.end_list()

        else:
            addon.show_error_dialog(["[B][COLOR red]No episodes found.[/COLOR][/B]"])
            return

    # identify forum sections/subsections
    def get_parents(self, linklist):
        newlist = []

        for l in linklist:
            if (l.has_key('id')):
                newlist.append(l)
            else:
                parent = newlist[-1]
                parent['data-has-children'] = True

        return newlist

    def action_browse_shows(self):
        remote_url = self.args['remote_url']
        logging.debug('browse show: %s' % remote_url)

        data = self.fetch(remote_url)
        soup = BeautifulSoup(data)

        sub = soup.find('ul', attrs={'data-role': 'listview', 'data-theme': 'd', 'class': 'forumbits'})
        h = sub.findAll('li')
        linklist = self.get_parents(h)

        for l in linklist:
            data = {}
            data.update(self.args)

            tagline = HTMLParser.HTMLParser().unescape(l.a.text)
            link = l.a['href']

            #if l.img['src'].find('new') > 0:
            #    tagline = '[COLOR green][B]+[/B][/COLOR] ' + tagline

            if l.has_key('data-has-children'):
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
            fid = re.compile('f(\d+)').findall(link)

            if len(fid) > 0:
                link = self.base_url + self.section_url_template + fid[0]

            data['Title'] = HTMLParser.HTMLParser().unescape(tagline)
            data['action'] = 'browse_episodes'
            data['remote_url'] = link
            self.add_list_item(data)
        self.end_list(sort_methods=(xbmcplugin.SORT_METHOD_LABEL,))

    def action_get_channel_menu(self):
        sequence = self.args['sequence']
        channels = []

        if (sequence == 'drama_channel_menu'):
            channels = self.drama_channel_menu
        elif (sequence == 'morning_shows_menu'):
            channels = self.morning_shows_menu
        elif (sequence == 'ramzan_shows_menu'):
            channels = self.ramzan_shows_menu
        elif (sequence == 'news_shows_menu'):
            channels = self.news_shows_menu

        for desc, link in channels:
            self.add_list_item({
                'Title': desc,
                'action': 'browse_shows',
                'remote_url': self.base_url + (self.section_url_template + link)
            })
        self.end_list(sort_methods=(xbmcplugin.SORT_METHOD_LABEL,))

    def action_get_urlresolver_settings(self):
        urlresolver.display_settings()

    def action_plugin_root(self):
        unavailable_msg = [
            "[B][COLOR red]Website is unavailable.[/COLOR][/B]",
            "This add-on cannot access the " + __plugin__ + " website.",
            "Please try again later."]

        try:
            response = requests.head(self.base_url)

            if response.status_code < 400:
                self.add_list_item({
                    'Title': '[B]Bookmarks[/B]',
                    'action': 'browse_bookmarks',
                    'folder_id': 1
                }, bookmark_parent=0)

                for desc, link in self.frame_menu:
                    self.add_list_item({
                        'Title': desc,
                        'action': 'browse_frames',
                        'remote_url': link
                    })

                self.add_list_item({
                    'Title': '[B]Browse Ramzan Specials[/B]',
                    'action': 'get_channel_menu',
                    'sequence': 'ramzan_shows_menu'
                })

                self.add_list_item({
                    'Title': '[B]Browse Pakistani Dramas[/B]',
                    'action': 'get_channel_menu',
                    'sequence': 'drama_channel_menu'
                })

                self.add_list_item({
                    'Title': '[B]Browse Morning/Cooking Shows[/B]',
                    'action': 'get_channel_menu',
                    'sequence': 'morning_shows_menu'
                })

                self.add_list_item({
                    'Title': '[B]Browse Current Affairs Talk Shows[/B]',
                    'action': 'get_channel_menu',
                    'sequence': 'news_shows_menu'
                })

                self.add_list_item({
                    'Title': '[B][COLOR white]Url Resolver Settings[/COLOR][/B]',
                    'action': 'get_urlresolver_settings'
                })

                self.end_list()

            else:
                addon.show_error_dialog(unavailable_msg)

        except:
                addon.show_error_dialog(unavailable_msg)

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
