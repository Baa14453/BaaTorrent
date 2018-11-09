import libtorrent
import time
import sys
import os
import ffmpeg
import feedparser
import urllib.request
import configparser
from subprocess import call

config = sys.argv[1]

location = sys.argv[2]

#Used for reading the RSS Feeds list
def import_config(config_file_name):
    config = configparser.RawConfigParser()

    config.read(config_file_name)

    rss_feeds = config['rss-feeds']
    latest_names = config['latest-name']
    svp = config['svp']

    #Return both headers inside the config file as a dictionary
    return rss_feeds, latest_names, svp

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

def download_torrent(torrent_source, save_location, output_file_name):
    #Start a session
    session = libtorrent.session({'listen_interfaces': '0.0.0.0:6881'})

    #Check if we are dealing with a torrent file or a magnet link
    if os.path.splitext(str(torrent_source))[1] == '.torrent':
        #Parse torrent file parameters
        torrent_info = libtorrent.torrent_info(download_file(torrent_source))
        torrent_in_progress = session.add_torrent({'ti': torrent_info, 'save_path': save_location})
        os.remove(torrent_source)
    else:
        #Parse magnet URI parameters
        torrent_info = libtorrent.parse_magnet_uri(torrent_source).get('info_hash')
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

    #time.sleep(1)

    #TODO test files with more than one . in the name
    output_file_name += str(os.path.splitext(str(torrent_in_progress.name()))[1])
    os.rename(torrent_in_progress.name(), output_file_name)

    print(torrent_in_progress.name(), 'complete')

    return output_file_name, torrent_in_progress.name()

def svp(temp_file_path, true_file_path):
    #Split file name
    true_file_path = os.path.splitext(str(true_file_path))
    final_file_path = true_file_path[0] + 'svp' + true_file_path[1]

    cmd = [f'vspipe svp.py -a file="{temp_file_path}" - --y4m | ffmpeg -i - -i "{temp_file_path}" -acodec copy -filter_complex "subtitles=\'{temp_file_path}\'"  "{final_file_path}" -y']
    call(cmd, shell=True)

    os.remove(temp_file_path)
    return final_file_path

def hardsub(temp_file_path, true_file_path):
    #Split file name
    true_file_path = os.path.splitext(true_file_path)
    final_file_path = 'videos/' + true_file_path[0] + 'hardsubs' + true_file_path[1]

    cmd = [f'ffmpeg -i "{temp_file_path}" -filter_complex "subtitles=\'{temp_file_path}\'"  "{final_file_path}" -y']
    call(cmd, shell=True)

    os.remove(temp_file_path)
    return final_file_path

def episode_parser(config_file_name, location):

    config = import_config(config_file_name)

    while True:
        for a in config[0]:
            #Process the RSS feed and retrieve the URL of the latest result.
            rss_result = feed_parser(str(config[0][str(a)]))
            if rss_result != (config[1][a]):

                #Download the torrent and save it to location.
                torrent = download_torrent(rss_result, location, a)
                #Save latest episode name

                write_config(config_file_name, a, rss_result)

                if config[2][a] == 'True':
                    #Interpolate
                    svp(torrent[0], torrent[1])
                else:
                    #Convert the downloaded torrent to hardsubs
                    hardsub(torrent[0], torrent[1])

            else:
                print(f'has not had a new release yet.')
        time.sleep(10)

episode_parser(config, location)
