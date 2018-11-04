import libtorrent
import time
import sys
import os
import ffmpeg
import feedparser
import urllib.request

rss_feed = sys.argv[1]

location = sys.argv[2]

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

def episode_parser(rss_feed, location):
    #Process the RSS feed and retrieve the URL of the latest result.
    rss_result = feed_parser(rss_feed)

    #Download the torrent and save it to location.
    torrent = download_torrent(rss_result, location)

    #Convert the downloaded torrent to hardsubs
    convert_video(torrent)

episode_parser(rss_feed, location)
#convert_video(download_torrent(magnet_to_torrent(feed_parser(rss_feed), location)[0],location))
