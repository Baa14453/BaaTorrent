from time import sleep
from sys import argv, stdout, exit, stderr
from os import path, remove, rename, linesep, X_OK, access, listdir, stat
from stat import S_ISDIR, S_ISREG
from configparser import ConfigParser, RawConfigParser, DuplicateOptionError
from feedparser import parse
from subprocess import Popen, CalledProcessError, run
from shutil import which
from ast import literal_eval
import subprocess
import urllib.request
import libtorrent
import logging

#TODO sanitise all config entries as int() or str()
#Used for settings.ini
def import_settings(settings_file_name):
    settings = ConfigParser()

    try:
        settings.read(settings_file_name)
    except DuplicateOptionError as e:
        logging.error(e)
        logging.debug('',exc_info=1)
        exit()
    except IOError:
        logging.error('Settings file \'{}\' could not be accessed.'.format(settings_file_name))
        logging.debug('',exc_info=1)
        exit()

    #Set debug mode.
    try:
        if settings['settings']['debug'] == '1':
            logging.getLogger().setLevel(logging.DEBUG)
            logging.debug('Debug logging is enabled.')
        else:
            logging.basicConfig(level=logging.INFO)
            settings['settings']['debug'] = '0'
            #Just in case...
            logging.debug('Debug logging is disabled.')
    except IndexError:
        logging.basicConfig(level=logging.INFO)
        settings['settings']['debug'] = '0'
        logging.debug('Debug logging is disabled.')

    #Set GPU enabled or disabled.
    try:
        if settings['settings']['gpu'] == '1':
            logging.debug(f'GPU interpolation enabled.')
        else:
            settings['settings']['gpu'] = '0'
            logging.debug(f'GPU interpolation disabled.')
    except IndexError:
        settings['settings']['gpu'] = '0'
        logging.debug(f'GPU interpolation disabled')


    #Set output file location.
    try:
        settings['settings']['location'] = path.abspath(settings['settings']['location'])
        logging.debug('Save location set to \'{}\''.format(settings['settings']['location']))
    except IndexError:
        settings['settings']['location'] = path.abspath(path.dirname(str(argv[0])))
        logging.info('Default save location \'{}\' in use.'.format(settings['settings']['location']))
        logging.debug('',exc_info=1)

    #Set rss check sleep time.
    #TODO create checks.
    try:
        #TODO What does this do?
        settings['settings']['rss_sleep_time']
        logging.debug('RSS sleep time set to {} seconds.'.format(settings['settings']['rss_sleep_time']))
    except IndexError:
        settings['settings']['rss_sleep_time'] = '600'
        logging.debug('RSS sleep time set to {} seconds.'.format(settings['settings']['rss_sleep_time']))
        logging.debug('',exc_info=1)

    #Set ffmpeg location.
    try:
        #Test if we can locate PATH application.
        if which(settings['settings']['ffmpeg_location']) != None:
            settings['settings']['ffmpeg_location'] = which(settings['settings']['ffmpeg_location'])
    except IndexError:
        settings['settings']['location'] = path.abspath(path.dirname(str(argv[0])))
        logging.info('Default save location \'{}\' in use.'.format(settings['settings']['location']))
        logging.debug('',exc_info=1)
     #Test ffmpeg works.
    try:
        ffmpeg_cmd = run([settings['settings']['ffmpeg_location'], '-no_banner'], universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.debug('FFMPEG found: {}'.format(ffmpeg_cmd.stderr.split("\n")[0]))
    except FileNotFoundError:
        logging.error('Cannot find FFMPEG: {}'.format(settings['settings']['ffmpeg_location']))
        logging.debug('',exc_info=1)

    #Set FFMS and SVP library locations, checks the files exist and are executable.
    LIBRARIES = 'ffms2', 'svpflow1', 'svpflow2'
    def library_checker(LIBRARIES):
        for file in LIBRARIES:
            if which(settings['settings'][file]) != None:
                #Changes relative path to full path in imported settings.
                settings['settings'][file] = which(settings['settings'][file])
                logging.debug('\'{}\' library location set to {}'.format(file, settings['settings'][file]))
            else:
                logging.debug('\'{}\' shutil.which result \'{}\' '.format(file, which(settings['settings'][file])))
                #shutil.which returned no path, something is wrong.
                if path.isfile(settings['settings'][file]):
                    #The file exists...
                    logging.debug('\'{}\' library \'{}\' exists.'.format(file, settings['settings'][file]))
                    #Is it executable?
                    if access(settings['settings'][file], X_OK):
                        #It is... something else is wrong.
                        logging.warn('\'{}\' library \'{}\' exists and is executable, unknown issue. Interpolation will fail.'.format(file, settings['settings'][file]))
                    else:
                        #It isn't, it will fail.
                        logging.warn('\'{}\' library \'{}\' exists but is not executable, interpolation will fail.'.format(file, settings['settings'][file]))
                else:
                    logging.warn('Cannot find \'{}\' library: \'{}\'; does not exist, interpolation will fail.'.format(file, settings['settings'][file]))

    library_checker(LIBRARIES)
    return settings

def import_rss(rss_file_path):
    #Process RSS config.
    rss = RawConfigParser()

    try:
        rss.read(rss_file_path)
    except DuplicateOptionError as e:
        logging.error(e)
        logging.debug('',exc_info=1)
        exit()
    except IOError:
        logging.error('RSS file \'{}\' could not be accessed.'.format(rss_file_path))
        logging.debug('',exc_info=1)
        exit()

    #Test rss config.
    try:
        #Check for the first value in 'rss_feeds'.
        list(rss['rss_feeds'])[0]
    except KeyError as Argument:
        logging.error(f'While parsing config header {Argument}.')
        logging.debug('',exc_info=1)
        exit()
    except IndexError:
        logging.error('No RSS feeds found in \'{}\'.'.format(rss_file_path))
        logging.debug('',exc_info=1)
        exit()

    #Check all keys in config are present.
    try:
        for key in rss['rss_feeds']:
            for header in rss:
                logging.debug(header)
                #Ignore DEFAULT header.
                if header != 'DEFAULT':
                    logging.debug('Checking config \'{}\' key \'{}\' in header \'{}\'.'.format(rss_file_path, key, header))
                    rss[header][key]
                    logging.debug('\'{}\' \'{}\' \'{}\' is OK.'.format(rss_file_path, header, key))

    except KeyError as Argument:
        logging.debug(f'Missing key for \'{header}\', attempting to fix.')
        logging.debug('',exc_info=1)
        write_config(rss_file_path, header, key, '')
        try:
            logging.debug('Reloading config \'{}\'.'.format(rss_file_path))
            #Test failed, try again.
            return 0
        except Exception as e:
            logging.error(f'While trying to fix key \'{key}\' for header \'{header}\'.')
            logging.debug('',exc_info=1)
            exit()

    return rss

#Used for saving details of last RSS feed used and repairing config.
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
def feed_parser(rss_feed, rss_mode):
    rss_result = parse(rss_feed)
    try:
        if rss_mode == "latest":
            return([[rss_result.entries[0].link, rss_result.entries[0].title]])
        elif rss_mode == "first":
            return([[rss_result.entries[-1].link, rss_result.entries[-1].title]])
        elif rss_mode == "all":
            entries = []
            for entry in rss_result.entries:
                entries.append([entry.link, entry.title])
                logging.debug(str(entries))
            return entries
        else:
            logging.error(f'Chosen RSS Mode \'{rss_mode}\' is not valid.')
            exit()

    #Catches empty RSS feeds.
    except IndexError as e:
        logging.warn(f'\'{rss_feed}\' has no entries or is not an RSS feed.')
        #TODO test just not returning anything.
        return

    #Not sure what will trigger this now, maybe broken rss feed?
    except Exception as e:
        logging.error(f'while parsing RSS feed \'{rss_feed}\'.')
        logging.debug('',exc_info=1)
        print(e, IndexError)
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

    #While loop of torrent downloading.
    while (not torrent_in_progress.is_seed()):
        status = torrent_in_progress.status()

        #Print download status every second.
        logging.info('{:.2f}% complete. (Speed: {:.1f} kB/s)'.format(status.progress * 100, status.download_rate / 1000))

        alerts = session.pop_alerts()
        for a in alerts:
            if a.category() & libtorrent.alert.category_t.error_notification:
                logging.error(f'{str(a)}')

        sleep(1)

    #TODO test files with more than one . in the name
    output_file_name += str(path.splitext(str(
                        torrent_in_progress.name()))[1])
    logging.info(f'{torrent_in_progress.name()} - Download complete.')

    output_file_path = f'{save_location}/{torrent_in_progress.name()}'
    #Return full path to the downloaded file/directory and the name of the torrent.
    return output_file_path, f'{torrent_in_progress.name()}'

#Interpolate the video to 60FPS and apply hardsubs
def process_video(file_path, video_mode, location):
    #Split file name
    #TODO what does this split on? check dots in filenames.
    final_file_path = path.splitext(file_path)
    final_file_path = final_file_path[0] + f'[{video_mode}]' + final_file_path[1]

    #Import config settings.
    gpu = settings['settings']['gpu']
    ffms2 = settings['settings']['ffms2']
    svpflow1 = settings['settings']['svpflow1']
    svpflow2 = settings['settings']['svpflow2']
    ffmpeg_binary = settings['settings']['ffmpeg_location']

    #Interpolate to 60FPS and apply hardsubs.
    if video_mode == "SVP+hardsub":
        logging.info(f'Starting interpolation and hardsub of: {file_path}')
        vspipe_cmd = ['vspipe', 'svp.py', '-a', f'file={file_path}', '-a', f'gpu={gpu}', '-a', f'ffms2={ffms2}', '-a', f'svpflow1={svpflow1}', '-a', f'svpflow2={svpflow2}', '-', '--y4m']

        ffmpeg_cmd = [ffmpeg_binary, '-i', '-', '-i', f'{file_path}', '-acodec', 'copy', \
               '-filter_complex', f'subtitles=\'{file_path}\'', \
               f'{final_file_path}', '-y', '-loglevel', 'warning', '-stats']

        #Start a process, assign it to vspipe.
        vspipe = Popen(vspipe_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        #Start a process, assign it to ffmpeg.
        ffmpeg = Popen(ffmpeg_cmd, stdin=vspipe.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    #Interpolate to 60FPS only.
    elif video_mode == "SVP":
        logging.info(f'Starting interpolation of: {file_path}')
        vspipe_cmd = ['vspipe', 'svp.py', '-a', f'file={file_path}', '-a', f'gpu={gpu}', '-a', f'ffms2={ffms2}', '-a', f'svpflow1={svpflow1}', '-a', f'svpflow2={svpflow2}', '-', '--y4m']

        ffmpeg_cmd = [ffmpeg_binary, '-i', '-', '-i', f'{file_path}', '-acodec', 'copy', \
               f'{final_file_path}', '-y', '-loglevel', 'warning', '-stats']

        #Start a process, assign it to vspipe.
        vspipe = Popen(vspipe_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        #Start a process, assign it to ffmpeg.
        ffmpeg = Popen(ffmpeg_cmd, stdin=vspipe.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    #Apply hardsubs only.
    elif video_mode == "hardsubs":
        logging.info(f'Starting hardsub of: {file_path}')
        ffmpeg_cmd = [ffmpeg_binary, '-i', f'{file_path}', '-c:a', 'copy', \
               f'{final_file_path}', '-y', '-loglevel', 'warning', '-stats']

        #Start a process, assign it to ffmpeg.
        ffmpeg = Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    #Do not process
    else:
        logging.info(f'Not processing video: {file_path}')
        return file_path

    #For each line of stderr (ffmpeg outputs to stderr for some reason).
    for stderr_line in ffmpeg.stderr:
        #Log only the last line.
        logging.info(stderr_line[:-1])
    #idk looks important though.
    ffmpeg.stderr.close()
    return_code = ffmpeg.wait()
    if return_code:
        logging.debug("FFMPEG err: " + str(ffmpeg.stderr))
        logging.debug("Input file: " + file_path)
        if video_mode == "SVP" or video_mode == "SVP+hardsubs":
            logging.debug("VSPipe cmd: " + str(vspipe_cmd))
        logging.debug("FFMPEG cmd: " + str(ffmpeg_cmd))
        raise CalledProcessError(return_code, ffmpeg_cmd)

    logging.info(f'Completed video processing of: {file_path}')
    logging.debug(f'Removing file {file_path}.')
    remove(file_path)
    if video_mode == "SVP" or video_mode == "SVP+hardsubs":
        logging.debug(f'Removing file {file_path}.ffindex.')
        remove(file_path + '.ffindex')

    return final_file_path

def videosearch(root):
    "Search directory structure for supported video files."
    supported_formats = ".mp4", ".avi", ".mkv"
    file_list = []
    #Use OS.STAT to get file permissions.
    mode = stat(root).st_mode
    #Use STAT.S_ISDIR to check if file permissions are from a directory.
    if (S_ISDIR(mode)):
        #It's a directory, recurse into it.
        logging.debug(f'Entering Directory: {root}')
        for found_file in listdir(root):
            for returned_file in videosearch(root + '/' + found_file):
                file_list.append(returned_file)
    elif S_ISREG(mode):
        #It's a file, check it's a supported format.
        for format in supported_formats:
            if root.endswith(format):
                logging.debug(f'Adding file to processing list: {root}')
                file_list.append(root)
    else:
        #Unknown file type, print a message
        logging.debug(f'Skipping {root}')

    return file_list

#Main function
def episode_parser():

    for rss_id in rss['rss_feeds']:
        #Process the RSS feed and retrieve the URL required (based on rss_mode).
        rss_results = feed_parser(rss['rss_feeds'][rss_id], rss['rss_mode'][rss_id])
        logging.debug(rss_results)
        for rss_result in rss_results:
            #Don't break if it's blank.
            if rss_result != None:
                #If latest rss result does not equal saved result...
                if rss_result[0] not in (rss['latest-name'][rss_id]):

                    #Download the torrent and save it to location under the name of
                    #it's rss id.
                    torrent = download_torrent(rss_result[0], settings['settings']['location'], rss_id)

                    #Find all videos
                    file_list = videosearch(torrent[0])
                    for file in file_list:
                        process_video(file, rss['rss_mode'][rss_id], settings['settings']['location'])

                    if rss['latest-name'][rss_id] == '':
                        #Value is blank so just write.
                        logging.debug(f'Value is blank writing \'{rss_result[0]}\'.')
                        write_config(settings['settings']['rss_config'], 'latest-name', rss_id, [str(rss_result[0])])
                    else:
                        #Value is not blank so check if the entry already exists.
                        logging.debug("Value is not blank so check if the entry already exists.")
                        latest_name = literal_eval(rss['latest-name'][rss_id])
                        if rss_result[0] not in latest_name:
                            logging.debug("Everything checks out, write the value.")
                            rss['latest-name'][rss_id] = str(latest_name + [rss_result[0]])
                            write_config(settings['settings']['rss_config'], 'latest-name', rss_id, rss['latest-name'][rss_id])
                        else:
                            logging.debug("Value already exists in config.")
                            return

                else:
                    logging.debug(rss_result)
                    logging.info(f'{rss_result[1]} is the latest release.')

if __name__ == "__main__":
    #Gather run arguments.
    try:
        SETTINGS_PATH = str(argv[1])
    except IndexError:
        logging.basicConfig(level=logging.INFO)
        logging.info('Default config path \'settings.ini\' in use.')
        SETTINGS_PATH = 'settings.ini'

    #Main loop.
    while True:
        try:
            #Load settings config.
            settings = import_settings(SETTINGS_PATH)
            #Import RSS
            #rss = 0 until import is successful.
            rss = 0
            while rss == 0:
                rss = import_rss(settings['settings']['rss_config'])
            #Run main function.
            episode_parser()
            #Wait 10 minutes.
            sleep(int(settings['settings']['rss_sleep_time']))
        except KeyboardInterrupt:
            logging.debug("Program terminated by user.")
            exit()
