import libtorrent
import time
import sys
import os
import ffmpeg
import feedparser
import urllib.request
import configparser

def import_config():
    config = configparser.RawConfigParser()

    config.read('rss.txt')

    rss_feeds = config['rss-feeds']
    latest_names = config['latest-name']

    return rss_feeds, latest_names

def write_config(key, value):
    config = configparser.RawConfigParser()
    config.read('rss.txt')

    #config.add_section('latest-name')
    #config.set('latest-name',str(key) ,str(value))
    config['latest-name'][str(key)] = str(value)

    with open('rss.txt', 'w') as config_file:
        config.write(config_file)

def feed_parser(rss_feed):

    d = feedparser.parse(rss_feed)

    return(d.entries[0].link)

#Used for downloading .torrent files
def download_file(url):
    file_name = os.path.basename(url)
    with urllib.request.urlopen(url) as response, open(file_name, 'wb') as out_file:
        data = response.read() # a `bytes` object
        out_file.write(data)
    return file_name

def download_torrent(torrent_sauce, save_location):
    #Start a session
    session = libtorrent.session({'listen_interfaces': '0.0.0.0:6881'})

    if os.path.splitext(str(torrent_sauce))[1] == '.torrent':
        #Parse torrent file parameters
        torrent_info = libtorrent.torrent_info(download_file(torrent_sauce))
        torrent_in_progress = session.add_torrent({'ti': torrent_info, 'save_path': save_location})
    else:
        #Parse magnet URI parameters
        torrent_info = libtorrent.parse_magnet_uri(torrent_sauce).get('info_hash')
        torrent_in_progress = session.add_torrent({'info_hash': torrent_info, 'save_path': save_location})

    return (torrent_in_progress.name())

def episode_parser(rss_feeds, location):

    for a in import_config()[1]:
        #Process the RSS feed and retrieve the URL of the latest result.
        rss_result = feed_parser(str(rss_feeds[str(a)]))
        #Download the torrent and save it to location.
        torrent = download_torrent(rss_result, location)
        #Save latest episode name
        #print (str(rss_feeds[str(a)]))
        write_config(a, str(torrent))

        #Convert the downloaded torrent to hardsubs
        #convert_video(torrent)

episode_parser(import_config()[0], '.')
