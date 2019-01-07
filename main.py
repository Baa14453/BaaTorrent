from time import sleep
from sys import argv, stdout, exit
from os import path, remove, rename
from configparser import RawConfigParser, DuplicateOptionError
import configparser
from feedparser import parse
from subprocess import call
import urllib.request
import libtorrent
import logging

#Used for reading the RSS Feeds list
def import_config(config_file_name):
    config = configparser.RawConfigParser()

    try:
        config.read(config_file_name)
    except DuplicateOptionError as e:
        logging.error(e)
        #logging.debug('',exc_info=1)
        exit()

    #Test config is imported correctly.
    try:
        rss_feeds = config['rss-feeds']
        latest_names = config['latest-name']
        svp = config['svp']

        #Check for the first value in 'rss-feeds'.
        list(config['rss-feeds'])[0]
    except IOError:
        logging.error(f"Config file '{config_file_name}' could not be accessed.")
        logging.debug('',exc_info=1)
        exit()
    except KeyError as Argument:
        logging.error(f'While parsing config header {Argument}.')
        logging.debug('',exc_info=1)
        exit()
    except IndexError:
        logging.error(f'No RSS feeds found in \'{config_file_name}\'.')
        logging.debug('',exc_info=1)
        exit()

    #Check all keys in config are present.
    try:
        for key in config['rss-feeds']:
            for header in config:
                #Ignore DEFAULT header.
                if header != 'DEFAULT':
                    logging.debug(f'Checking config \'{config_file_name}\' key \'{key}\' in header \'{header}\'.')
                    config[header][key]
                    logging.debug(f'\'{config_file_name}\' \'{header}\' \'{key}\' is OK.')
    except KeyError as Argument:
        logging.debug(f'Missing key for \'{header}\', attempting to fix.')
        logging.debug('',exc_info=1)
        write_config(config_file_name, header, key, '')
        try:
            logging.debug(f'Reloading config \'{config_file_name}\'.')
            rss_feeds, latest_names, svp = import_config(config_file_name)
        except exception as e:
            logging.error(f'While trying to fix key \'{key}\' for header \'{header}\'.')
            logging.debug('',exc_info=1)
            exit()

    #Return all headers inside the config file as a dictionary
    return rss_feeds, latest_names, svp

#Used for saving details of last RSS feed used.
def write_config(config_file_name, header, key, value):
    config = RawConfigParser()
    config.read(config_file_name)

    config[str(header)][str(key)] = str(value)

    with open(str(config_file_name), 'w') as config_file:
        config.write(config_file)

#Used for downloading .torrent files
def download_file(url):
    file_name = path.basename(url)
    with urllib.request.urlopen(url) as response, \
         open(file_name, 'wb') as out_file:
        data = response.read() # a `bytes` object
        out_file.write(data)

    return file_name

#Processes an RSS feed, returns the link and title attributes.
def feed_parser(rss_feed):
    d = parse(rss_feed)
    try:
        return(d.entries[0].link, d.entries[0].title)
    except IndexError as e:
        logging.error(f'while parsing RSS feed \'{rss_feed}\'.')
        exit()

#Processes a torrent downloading it and returning the output file's location.
def download_torrent(torrent_source, save_location, output_file_name):
    #Start a session
    session = libtorrent.session({'listen_interfaces': '0.0.0.0:6881'})

    #Check if we are dealing with a torrent file or a magnet link
    if torrent_source.endswith('.torrent'):
        #Parse torrent file parameters
        torrent_file = download_file(torrent_source)
        torrent_info = libtorrent.torrent_info(torrent_file)
        torrent_in_progress = session.add_torrent({
                                                'ti': torrent_info,
                                                'save_path': save_location
                                                })
        remove(torrent_file)
    else:
        #Parse magnet URI parameters
        torrent_info = libtorrent.parse_magnet_uri(torrent_source).get('info_hash')
        torrent_in_progress = session.add_torrent({
                                                'ti': torrent_info,
                                                'save_path': save_location
                                                })

    logging.info(f'Starting download: {torrent_in_progress.name()}.')

    while (not torrent_in_progress.is_seed()):
        status = torrent_in_progress.status()

        sleep(1)
        logging.info('{:.2f}% complete. (Speed: {:.1f} kB/s)'.format(status.progress * 100, status.download_rate / 1000))

        alerts = session.pop_alerts()
        for a in alerts:
            if a.category() & libtorrent.alert.category_t.error_notification:
                logging.error(f'{str(a)}')

    #TODO test files with more than one . in the name
    output_file_name += str(path.splitext(str(
                        torrent_in_progress.name()))[1])

    rename(f'{save_location}/{torrent_in_progress.name()}', f'{save_location}/{output_file_name}')
    logging.info(f'{torrent_in_progress.name()} - Download complete.')

    #return output_file_name, torrent_in_progress.name()
    return f'{save_location}/{output_file_name}', f'{torrent_in_progress.name()}'

#Interpolate the video to 60FPS and apply hardsubs
def svp(temp_file_path, true_file_path, location):
    logging.info('Starting  interpolation:')
    #Split file name
    true_file_path = path.splitext(str(true_file_path))
    final_file_path = location + '/' + true_file_path[0] + 'svp' + true_file_path[1]

    cmd = [f'vspipe svp.py -a file="{temp_file_path}" - --y4m |\
           ffmpeg -i - -i "{temp_file_path}" -acodec copy \
           -filter_complex "subtitles=\'{temp_file_path}\'" \
           "{final_file_path}" -y -loglevel warning -stats']

    call(cmd, shell=True)
    logging.info(f'Interpolation complete.')

    logging.debug(f'Removing file {temp_file_path}.')
    remove(temp_file_path)
    logging.debug(f'Removing file {temp_file_path}.ffindex.')
    remove(temp_file_path + '.ffindex')

    return final_file_path

#Re-encode the video to apply hardsubs
def hardsub(temp_file_path, true_file_path, location):
    logging.info('Applying hardsubs:')
    #Split file name
    true_file_path = path.splitext(true_file_path)
    final_file_path = location + '/' + true_file_path[0] + 'hardsubs' + true_file_path[1]

    cmd = [f'ffmpeg -i "{temp_file_path}" \
           -filter_complex "subtitles=\'{temp_file_path}\'" \
           "{final_file_path}" -y -loglevel warning -stats']

    call(cmd, shell=True)
    print('Hardsub rendering complete.')

    logging.debug(f'Removing file {temp_file_path}.')
    remove(temp_file_path)

    return final_file_path

#Main function
def episode_parser(config_file_name, location):

    config = import_config(config_file_name)

    while True:
        for config_id in config[0]:
            #Process the RSS feed and retrieve the URL of the latest result.
            rss_result = feed_parser(str(config[0][str(config_id)]))
            #If latest rss result does not equal saved result...
            if rss_result[0] != (config[1][config_id]):

                #Download the torrent and save it to location under the name of
                #it's config number.
                torrent = download_torrent(rss_result[0], location, config_id)

                #Check if the current iteration has SVP set to True or not.
                if config[2][config_id] == 'True':
                    #Interpolate
                    svp(torrent[0], torrent[1], location)
                else:
                    #Convert the downloaded torrent to hardsubs.
                    hardsub(torrent[0], torrent[1], location)

                #The process is completed, save latest RSS link to config.
                write_config(config_file_name, 'latest-name', config_id, rss_result[0])

            else:
                print(f'{rss_result[1]} is the latest release.')
        #Wait 10 minutes
        sleep(600)
        #Redefine config so it can be checked again.
        config = import_config(config_file_name)

if __name__ == "__main__":
    #logging.basicConfig(level=logging.INFO)
    logging.basicConfig(level=logging.DEBUG)
    #Gather run arguments
    try:
        config = str(argv[1])
    except IndexError:
        logging.info('Default path \'rss.txt\' in use.')
        config = 'rss.ini'
    try:
        location = str(argv[2])
    except IndexError:
        logging.info('Default save location \'.\' in use.')
        location = '.'

    #Run main function
    try:
        episode_parser(config, location)
    except KeyboardInterrupt:
        logging.debug("\nProgram terminated by user.")
