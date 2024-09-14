#!/usr/bin/python
# -*- coding: utf-8 -*-

# Standard library imports
import json
import os
from datetime import datetime

try:
    from http.client import HTTPConnection
    HTTPConnection.debuglevel = 0
except ImportError:
    from httplib import HTTPConnection
    HTTPConnection.debuglevel = 0

# Third-party imports
from requests.adapters import HTTPAdapter, Retry

# Enigma2 components
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Screens.Console import Console
from Screens.Screen import Screen
from enigma import eServiceReference, iPlayableService, eTimer
from Components.ServiceEventTracker import ServiceEventTracker
from Screens.MessageBox import MessageBox
from Components.Pixmap import Pixmap

# Local application/library-specific imports
from . import _
from . import xklass_globals as glob
from . import processfiles as loadfiles
from .plugin import (cfg, downloads_json, hasConcurrent, hasMultiprocessing, playlists_json, pythonFull, skin_directory, version, InternetSpeedTest_installed, NetSpeedTest_installed)
from .xStaticText import StaticText
from . import checkinternet

hdr = {'User-Agent': str(cfg.useragent.value)}


class XKlass_MainMenu(Screen):
    ALLOW_SUSPEND = True

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        skin_path = os.path.join(skin_directory, cfg.skin.value)

        skin = os.path.join(skin_path, "startmenu.xml")
        with open(skin, "r") as f:
            self.skin = f.read()

        self.list = []
        self.drawList = []
        self["list"] = List(self.drawList, enableWrapAround=True)

        self["background"] = StaticText("")
        # self["background"].hide()

        self.setup_title = _("Main Menu")

        self["provider"] = StaticText()

        self["version"] = StaticText()

        actions = {
            "green": self.__next__,
            "ok": self.__next__,
            "left": self.goUp,
            "right": self.goDown,
            "menu": self.mainSettings,
            "help": self.resetData,
            "blue": self.resetData
        }

        if not cfg.boot.value:
            actions.update({"red": self.quit, "cancel": self.quit})

        self["actions"] = ActionMap(["XKlassActions"], actions, -2)

        self["version"].setText(version)

        self.playlists_all = loadfiles.process_files()

        self.defaultplaylist = cfg.defaultplaylist.value
        self.lastcategory = cfg.lastcategory.value

        glob.active_playlist = []

        try:
            glob.currentPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.currentPlayingServiceRefString = self.session.nav.getCurrentlyPlayingServiceReference().toString()
            glob.newPlayingServiceRef = self.session.nav.getCurrentlyPlayingServiceReference()
            glob.newPlayingServiceRefString = glob.newPlayingServiceRef.toString()
        except:
            pass

        self.tracker = ServiceEventTracker(screen=self, eventmap={
            iPlayableService.evEOF: self.onEOF
        })

        if not cfg.backgroundsat.value:
            self.session.nav.stopService()
        self.onLayoutFinish.append(self.__layoutFinished)
        self.onFirstExecBegin.append(self.check_dependencies)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def check_dependencies(self):
        dependencies = True

        try:
            import requests
            from PIL import Image
            # print("***** python version *** %s" % pythonFull)
            if pythonFull < 3.9:
                # print("*** checking multiprocessing ***")
                from multiprocessing.pool import ThreadPool
        except Exception as e:
            # print("**** missing dependencies ***")
            print(e)
            dependencies = False

        if dependencies is False:
            os.chmod("/usr/lib/enigma2/python/Plugins/Extensions/XKlass/dependencies.sh", 0o0755)
            cmd1 = ". /usr/lib/enigma2/python/Plugins/Extensions/XKlass/dependencies.sh"
            self.session.openWithCallback(self.start, Console, title="Checking Python Dependencies", cmdlist=[cmd1], closeOnSuccess=False)
        else:
            self.start()

    def start(self, answer=None):
        if not checkinternet.check_internet():
            self.session.openWithCallback(self.quit, MessageBox, _("No internet."), type=MessageBox.TYPE_ERROR, timeout=5)

        if not self.playlists_all:
            self.addServer()
            self.close()
        else:
            self.selectplaylist()

    def addServer(self):
        from . import server
        self.session.openWithCallback(self.quit, server.XKlass_AddServer)

    def selectplaylist(self):
        if self.playlists_all:
            p = 0
            exists = False
            for playlist in self.playlists_all:
                if str(playlist["playlist_info"]["name"]) == self.defaultplaylist:
                    glob.active_playlist = playlist
                    glob.current_selection = p
                    exists = True
                    break

                p += 1

            if not exists:
                cfg.defaultplaylist.setValue(str(self.playlists_all[0]["playlist_info"]["name"]))
                cfg.save()
                glob.active_playlist = self.playlists_all[0]
                glob.current_selection = 0

            self.player_api = glob.active_playlist["playlist_info"]["player_api"]

            self.p_live_categories_url = str(self.player_api) + "&action=get_live_categories"
            self.p_vod_categories_url = str(self.player_api) + "&action=get_vod_categories"
            self.p_series_categories_url = str(self.player_api) + "&action=get_series_categories"
            self.p_live_streams_url = str(self.player_api) + "&action=get_live_streams"

            glob.active_playlist["data"]["live_streams"] = []
            self.original_active_playlist = glob.active_playlist
        else:
            cfg.defaultplaylist.setValue("")
            cfg.save()

        self.makeUrlList()

    def makeUrlList(self):
        self.url_list = []
        glob.active_playlist["data"]["live_categories"] = []
        glob.active_playlist["data"]["vod_categories"] = []
        glob.active_playlist["data"]["series_categories"] = []
        glob.active_playlist["data"]["live_streams"] = []
        glob.active_playlist["data"]["catchup"] = False
        glob.active_playlist["data"]["customsids"] = False
        glob.active_playlist["data"]["data_downloaded"] = False

        player_api = str(glob.active_playlist["playlist_info"].get("player_api", ""))
        full_url = str(glob.active_playlist["playlist_info"].get("full_url", ""))
        domain = str(glob.active_playlist["playlist_info"].get("domain", ""))
        username = str(glob.active_playlist["playlist_info"].get("username", ""))
        password = str(glob.active_playlist["playlist_info"].get("password", ""))
        if "get.php" in full_url and domain and username and password:
            self.url_list.append([player_api, 0])
            self.url_list.append([self.p_live_categories_url, 1])
            self.url_list.append([self.p_vod_categories_url, 2])
            self.url_list.append([self.p_series_categories_url, 3])

            if glob.active_playlist["data"]["data_downloaded"] is False:
                self.url_list.append([self.p_live_streams_url, 4])

        self.process_downloads()

    def download_url(self, url):
        import requests
        index = url[1]
        response = None

        retries = Retry(total=2, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retries)

        with requests.Session() as http:
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            try:
                # Perform the initial request
                r = http.get(url[0], headers=hdr, timeout=6, verify=False)
                r.raise_for_status()

                if 'application/json' in r.headers.get('Content-Type', ''):
                    try:
                        response = r.json()
                    except ValueError as e:
                        print("Error decoding JSON:", e, url)
                else:
                    print("Error: Response is not JSON", url)

            except Exception as e:
                print("Unexpected error:", e)
                self.session.open(MessageBox, _("Server not responding."), type=MessageBox.TYPE_INFO, timeout=5)

        return index, response

    def process_downloads(self):
        threads = min(len(self.url_list), 4)
        results = ""
        self.retry = 0
        all_failed = True

        if hasConcurrent or hasMultiprocessing:
            if hasConcurrent:
                try:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=threads) as executor:
                        results = list(executor.map(self.download_url, self.url_list))
                except Exception as e:
                    print("Concurrent execution error:", e)

            elif hasMultiprocessing:
                # print("********** trying multiprocessing threadpool *******")
                try:
                    from multiprocessing.pool import ThreadPool
                    pool = ThreadPool(threads)
                    results = pool.imap_unordered(self.download_url, self.url_list)
                    pool.close()
                    pool.join()
                except Exception as e:
                    print("Multiprocessing execution error:", e)

            if results:
                for index, response in results:
                    if response:
                        if index == 0:
                            if "user_info" in response:
                                if response["user_info"]["status"] != "Active":
                                    self.session.openWithCallBack(self.showPlaylists, MessageBox, _("Playlist not active."), type=MessageBox.TYPE_INFO, timeout=5)
                                    return
                                else:
                                    glob.active_playlist.update(response)
                            else:
                                glob.active_playlist["user_info"] = {}
                                self.showPlaylists()
                                return
                        elif index in [1, 2, 3, 4]:
                            all_failed = False

                            if index == 1:
                                glob.active_playlist["data"]["live_categories"] = response

                            if index == 2:
                                glob.active_playlist["data"]["vod_categories"] = response

                            if index == 3:
                                glob.active_playlist["data"]["series_categories"] = response

                            if index == 4:
                                glob.active_playlist["data"]["live_streams"] = response

        else:
            # print("*** trying sequential ***")
            for url in self.url_list:
                result = self.download_url(url)
                if result:
                    index = result[0]
                    response = result[1]
                    if response:
                        if index == 0:
                            if "user_info" in response:
                                if response["user_info"]["status"] != "Active":
                                    self.session.openWithCallBack(self.showPlaylists, MessageBox, _("Playlist not active."), type=MessageBox.TYPE_INFO, timeout=5)
                                    return
                                else:
                                    glob.active_playlist.update(response)
                            else:
                                glob.active_playlist["user_info"] = {}
                                self.showPlaylists()
                                return
                        elif index in [1, 2, 3, 4]:
                            all_failed = False

                            if index == 1:
                                glob.active_playlist["data"]["live_categories"] = response

                            if index == 2:
                                glob.active_playlist["data"]["vod_categories"] = response

                            if index == 3:
                                glob.active_playlist["data"]["series_categories"] = response

                            if index == 4:
                                glob.active_playlist["data"]["live_streams"] = response

        if all_failed:
            self.showPlaylists()

        glob.active_playlist["data"]["data_downloaded"] = True
        self.createSetup()

    def reload(self, Answer=None):
        self["list"].setIndex(0)

        if self.original_active_playlist != glob.active_playlist:
            self.player_api = glob.active_playlist["playlist_info"]["player_api"]
            self.p_live_categories_url = str(self.player_api) + "&action=get_live_categories"
            self.p_vod_categories_url = str(self.player_api) + "&action=get_vod_categories"
            self.p_series_categories_url = str(self.player_api) + "&action=get_series_categories"
            self.p_live_streams_url = str(self.player_api) + "&action=get_live_streams"

            self.original_active_playlist = glob.active_playlist

            self.makeUrlList()
        else:
            self.createSetup()

    def createSetup(self):
        self.provider = str(glob.active_playlist["playlist_info"]["name"])
        self["provider"].setText(self.provider)

        if cfg.introvideo.value:
            self.playVideo()
        else:
            self["background"].setText("True")

        def add_category_to_list(title, category_type, index):
            if category_type in glob.active_playlist["data"] and glob.active_playlist["data"][category_type]:
                if "category_id" in glob.active_playlist["data"][category_type][0] and "user_info" not in glob.active_playlist["data"][category_type]:
                    self.index += 1
                    self.list.append([self.index, _(title), index])

        self.list = []
        self.index = 0
        downloads_all = []
        if os.path.isfile(downloads_json) and os.stat(downloads_json).st_size > 0:
            try:
                with open(downloads_json, "r") as f:
                    downloads_all = json.load(f)
            except Exception as e:
                print(e)

        show_live = glob.active_playlist["player_info"].get("showlive", False)
        show_vod = glob.active_playlist["player_info"].get("showvod", False)
        show_series = glob.active_playlist["player_info"].get("showseries", False)
        show_catchup = glob.active_playlist["player_info"].get("showcatchup", False)

        content = glob.active_playlist["data"]["live_streams"]

        has_catchup = any(str(item.get("tv_archive", "0")) == "1" for item in content if "tv_archive" in item)
        has_custom_sids = any(item.get("custom_sid", False) for item in content if "custom_sid" in item)

        glob.active_playlist["data"]["live_streams"] = []

        if has_custom_sids:
            glob.active_playlist["data"]["customsids"] = True

        if has_catchup:
            glob.active_playlist["data"]["catchup"] = True

        if show_live:
            add_category_to_list("Live TV", "live_categories", 0)

        if show_vod:
            add_category_to_list("Movies", "vod_categories", 1)

        if show_series:
            add_category_to_list("Series", "series_categories", 2)

        if show_catchup and glob.active_playlist["data"]["catchup"]:
            self.index += 1
            self.list.append([self.index, _("Catch Up TV"), 3])

        self.list.append([self.index, _("Switch Playlist"), 6])

        self.list.append([self.index, _("Global Settings"), 4])

        self.index += 1

        if downloads_all:
            self.index += 1
            self.list.append([self.index, _("Download Manager"), 5])

        if cfg.boot.value:
            self.index += 1
            self.list.append([self.index, _("Reboot GUI"), 7])

        if cfg.speedtest.value and (InternetSpeedTest_installed is True or NetSpeedTest_installed is True):
            self.index += 1
            self.list.append([self.index, _("Speed Test"), 8])

        self.drawList = [buildListEntry(x[0], x[1], x[2]) for x in self.list]
        self["list"].setList(self.drawList)

        self.writeJsonFile()

    def writeJsonFile(self):
        with open(playlists_json, "r") as f:
            playlists_all = json.load(f)

        playlists_all[glob.current_selection] = glob.active_playlist

        with open(playlists_json, "w") as f:
            json.dump(playlists_all, f)

    def __next__(self):
        if cfg.introvideo.value:

            if cfg.backgroundsat.value:

                try:
                    if glob.currentPlayingServiceRefString:
                        self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
                except Exception as e:
                    print(e)

            else:
                self.session.nav.stopService()

        current_entry = self["list"].getCurrent()

        if current_entry:
            index = current_entry[2]
            if index == 0:
                self.showLive()
            elif index == 1:
                self.showVod()
            elif index == 2:
                self.showSeries()
            elif index == 3:
                self.showCatchup()
            elif index == 4:
                self.mainSettings()
            elif index == 5:
                self.downloadManager()
            elif index == 6:
                self.showPlaylists()
            elif index == 7:
                self.ExecuteRestart()
            elif index == 8:
                self.runSpeedTest()

    def runSpeedTest(self):
        if InternetSpeedTest_installed:
            from Plugins.Extensions.InternetSpeedTest.plugin import internetspeedtest
            self.session.openWithCallback(self.reload, internetspeedtest)
        elif NetSpeedTest_installed:
            from Plugins.Extensions.NetSpeedTest.default import NetSpeedTestScreen
            self.session.openWithCallback(self.reload, NetSpeedTestScreen)

    def ExecuteRestart(self, result=None):
        from Screens import Standby
        Standby.quitMainloop(3)

    def showLive(self):
        from . import live
        self.session.openWithCallback(self.reload, live.XKlass_Live_Categories)

    def showVod(self):
        from . import vod
        self.session.openWithCallback(self.reload, vod.XKlass_Vod_Categories)

    def showSeries(self):
        from . import series
        self.session.openWithCallback(self.reload, series.XKlass_Series_Categories)

    def showCatchup(self):
        from . import catchup
        self.session.openWithCallback(self.reload, catchup.XKlass_Catchup_Categories)

    def mainSettings(self):
        from . import settings
        self.session.openWithCallback(self.reload, settings.XKlass_Settings)

    def downloadManager(self):
        from . import downloadmanager
        self.session.openWithCallback(self.reload, downloadmanager.XKlass_DownloadManager)

    def showPlaylists(self):
        from . import playlists
        self.session.openWithCallback(self.reload, playlists.XKlass_Playlists)

    def quit(self, data=None):
        self.playOriginalChannel()

    def playOriginalChannel(self):
        # self.stopVideo()
        try:
            if glob.currentPlayingServiceRefString:
                self.session.nav.playService(eServiceReference(glob.currentPlayingServiceRefString))
        except Exception as e:
            print(e)

        self.close()

    def playVideo(self, result=None):
        self["background"].setText("")
        self.local_video_path = cfg.introvideoselection.value
        service = eServiceReference(4097, 0, self.local_video_path)
        self.session.nav.playService(service)

    def onEOF(self):
        if cfg.introvideo.value and cfg.introloop.value:
            self["background"].setText("")
            service = self.session.nav.getCurrentService()
            seek = service and service.seek()
            if seek:
                seek.seekTo(0)
        else:
            self["background"].setText("True")

    def goUp(self):
        instance = self["list"].master.master.instance
        instance.moveSelection(instance.moveUp)

    def goDown(self):
        instance = self["list"].master.master.instance
        instance.moveSelection(instance.moveDown)

    def resetData(self, answer=None):
        if answer is None:
            self.session.openWithCallback(self.resetData, MessageBox, _("Warning: delete stored json data for all playlists... Settings, favourites etc. \nPlaylists will not be deleted.\nDo you wish to continue?"))
        elif answer:
            try:
                os.remove(playlists_json)
                with open(playlists_json, "a"):
                    pass
            except OSError as e:
                print("Error deleting or recreating JSON file:", e)
            self.quit()


def buildListEntry(index, title, num):
    return index, str(title), num
