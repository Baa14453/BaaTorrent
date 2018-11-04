import libtorrent
import time
import sys
import os
import ffmpeg
import feedparser
import urllib.request
import configparser

config = sys.argv[1]

location = sys.argv[2]

#Used for reading the RSS Feeds list
def import_config(config_file_name):
    config = configparser.RawConfigParser()

    config.read(config_file_name)

    rss_feeds = config['rss-feeds']
    latest_names = config['latest-name']

    #Return both headers inside the config file as a dictionary
    return rss_feeds, latest_names

#Used for saving details of last RSS feed used.
def write_config(config_file_name, key, value):
    config = configparser.RawConfigParser()
    config.read(config_file_name)

    config['latest-name'][str(key)] = str(value)

    with open(str(config_file_name), 'w') as config_file:
        config.write(config_file)

#Used for downloading .torrent files
def download_file(url):
    file_name = os.path.basename(url)
    with urllib.request.urlopen(url) as response, open(file_name, 'wb') as out_file:
        data = response.read() # a `bytes` object
        out_file.write(data)
    return file_name

def feed_parser(rss_feed):

    d = feedparser.parse(rss_feed)

    return(d.entries[0].link)

def download_torrent(torrent_sauce, save_location):
    #Start a session
    session = libtorrent.session({'listen_interfaces': '0.0.0.0:6881'})

    #Check if we are dealing with a torrent file or a magnet link
    if os.path.splitext(str(torrent_sauce))[1] == '.torrent':
        #Parse torrent file parameters
        torrent_info = libtorrent.torrent_info(download_file(torrent_sauce))
        torrent_in_progress = session.add_torrent({'ti': torrent_info, 'save_path': save_location})
    else:
        #Parse magnet URI parameters
        torrent_info = libtorrent.parse_magnet_uri(torrent_sauce).get('info_hash')
        torrent_in_progress = session.add_torrent({'info_hash': torrent_info, 'save_path': save_location})

    print('starting', torrent_in_progress.name())

    while (not torrent_in_progress.is_seed()):
        status = torrent_in_progress.status()

        print('\r%.2f%% complete (down: %.1f kB/s up: %.1f kB/s peers: %d) %s' % \
        (status.progress * 100, status.download_rate / 1000, status.upload_rate / 1000, \
        status.num_peers, status.state), end=' ')

        alerts = session.pop_alerts()
        for a in alerts:
            if a.category() & libtorrent.alert.category_t.error_notification:
                print(a)

    sys.stdout.flush()

    time.sleep(1)

    print(torrent_in_progress.name(), 'complete')
    return torrent_in_progress.name()

def convert_video(file_path):
    #Split file name
    file_path_tuple = os.path.splitext(str(file_path))

    #Create a stream
    stream = ffmpeg.input(file_path)

    #Apply subtitle filter
    stream = ffmpeg.filter_(stream,'subtitles',str(file_path))

    #Remap audio :/
    stream = ffmpeg.output(stream, file_path_tuple[0] + '2' + file_path_tuple[1], map='0:1')

    #Ovewrite the file if it's there
    stream = ffmpeg.overwrite_output(stream)

    #Get to work
    ffmpeg.run(stream)

def episode_parser(config_file_name, location):

    config = import_config(config_file_name)

    while True:
        for a in config[0]:
            #Process the RSS feed and retrieve the URL of the latest result.
            rss_result = feed_parser(str(config[0][str(a)]))
            if rss_result != (config[1][a]):

                #Download the torrent and save it to location.
                torrent = download_torrent(rss_result, location)
                #Save latest episode name
                write_config(config_file_name, a, rss_result)

                #Convert the downloaded torrent to hardsubs
                #convert_video(torrent)
            else:
                print(f'has not had a new release yet.')
        time.sleep(10)

episode_parser(config, location)
#convert_video(download_torrent(magnet_to_torrent(feed_parser(rss_feed), location)[0],location))
