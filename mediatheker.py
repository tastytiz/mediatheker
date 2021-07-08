import packages
import logging
from tinydb import TinyDB, Query
import yaml
from shutil import copyfile
from datetime import datetime
import argparse
import json
import os


#initialize argument parser
my_parser = argparse.ArgumentParser(description='little app to send out newsletters with the latest movies available on German public broadcast channels.')

# initialize first run script
first_run = packages.FirstRun()
first_run_counter = 0

# set script config
if not os.path.exists('config.yaml'):
    first_run.start_config()
    first_run_counter +=1

config_yaml = open('config.yaml','r')
config = yaml.load(config_yaml, Loader=yaml.FullLoader)
config_yaml.close()

# set logger
logger = logging.getLogger('mediatheker')
logger.setLevel(logging.INFO)

fh = logging.FileHandler('mediatheker.log')
fh.setLevel(logging.INFO)
fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(message)s'))
logger.addHandler(fh)

# set database + operations
if not os.path.exists(config['DB']['path']):
    first_run.start_db()
    first_run_counter +=1

db = TinyDB(config['DB']['path'])
available_movies = db.table(config['DB']['available_movies'])
latest_movies = db.table(config['DB']['latest_movies'])
subscribers = db.table(config['DB']['subscribers'])
run_info = db.table(config['DB']['run_info'])
first_seen = db.table(config['DB']['first_seen'])
Query_obj = Query()

# if first_run was called at least once, check if user can/wants to set a cronjob
if first_run_counter > 0:
    first_run.start_cronjob()

# initialize package classes
mailer = packages.Mailer(config, subscribers, available_movies)
movret = packages.Movieretriever(config, latest_movies, available_movies, first_seen)

# set arguments
# Add the arguments
my_parser.add_argument('-s', '--score', action='store_true',help='returns list of available movies and their imdb matchmaking scores.')
my_parser.add_argument('-l', '--load', action='store_true', help='retrieves new movies and sends out the newsletter to all users.')
my_parser.add_argument('-sub', '--subscribers', action='store_true', help='retrieves all subscribers from database.')
my_parser.add_argument('-g', '--get_movie', action='store', help='search & return for specific movie in database using its title.')
my_parser.add_argument('-a', '--admin', action='store', help='set admin.')
my_parser.add_argument('-t', '--test', action='store_true', help='make a test run which loads data and sends it to the admin only.')

# Execute parse_args()
args = my_parser.parse_args()


# check if test database exists. If so, replace current db and remove test
if os.path.exists(config['DB']['test_path']):
    copyfile(config['DB']['test_path'], config['DB']['path'])
    os.remove(config['DB']['test_path'])

if args.test:
    copyfile(config['DB']['path'], config['DB']['test_path'])

    latest_movies.truncate()

    logger.info("Starting TEST with {latest} movies in {latest_name} and {available} movies in {available_name}.".format(latest=len(latest_movies),latest_name=config['DB']['latest_movies'], available=len(available_movies),available_name=config['DB']['available_movies']))

    retrieval_success = movret.retrieve_movies() # retrieve movies
    # retrieval_success = True
    if retrieval_success:
        logger.info('{counter} movies retrieved'.format(counter=len(latest_movies)))
        movret.update_movie_list()
        logger.info('{counter} movies updated'.format(counter=len(available_movies)))
        curr_admin = subscribers.get(Query_obj.admin == True)
        send_counter, update_counter = mailer.send_newsletter(curr_admin)
        logger.info(f'TEST Mail successfully sent to {curr_admin["email"]}.')
    else:
        logger.error('Error while retrieving the movies. Script stops here.')
    copyfile(config['DB']['test_path'], config['DB']['path'])
    os.remove(config['DB']['test_path'])



if args.load:
    # backup database. Overwrite every night
    copyfile(config['DB']['path'], config['DB']['backup_path'])

    #0. set run_info
    current_run = datetime.now()
    run_info.insert({'run_start' : str(current_run), 'run_end' : '', 'status' : 'started'})

    #1. retrieve movies from mediatheks

    latest_movies.truncate()

    logger.info("Starting with {latest} movies in {latest_name} and {available} movies in {available_name}.".format(latest=len(latest_movies),latest_name=config['DB']['latest_movies'], available=len(available_movies),available_name=config['DB']['available_movies']))

    retrieval_success = movret.retrieve_movies() # retrieve movies
    # retrieval_success = True
    if retrieval_success:
        logger.info('{counter} movies retrieved'.format(counter=len(latest_movies)))
        #-------------
        # #test
        # movie_list.to_csv('res/test/movie_list.csv',index=False,encoding='utf-8')
        # movie_list = pd.read_csv('dev/movieList_test.csv',encoding='utf-8')
        #----------

        #2. update movie list with changes and add iMDb info
        movret.update_movie_list()

        logger.info('{counter} movies updated'.format(counter=len(available_movies)))
        #-------------
        #test
        # movies_updated = pd.read_csv('res/movieList.csv',encoding='utf-8')
        #-------------

        #3. send newsletter to subscribers
        send_counter, update_counter = mailer.send_newsletter()

        logger.info(f'Mails successfully sent to {send_counter}/{len(subscribers)} user(s). {update_counter} new user(s) registered.')

        #save success message to db
        run_info.update({'status' : 'success', 'run_end': str(datetime.now())}, Query_obj.run_start == str(current_run))
        duration = datetime.now() - current_run
        logger.info(f'Script ended successfully after {str(duration)}.')
    else:
        run_info.update({'status' : 'failed', 'run_end': str(datetime.now())}, Query_obj.run_start == str(current_run))
        logger.error('Error while retrieving the movies. Script stops here.')

if args.score:
    logger.info('returning scores for iMDb matchmaking')
    for movie in available_movies:
        if 'score' in movie:
            curr_score = str(movie['score']) if movie['score'] >= 10 else '0' + str(movie['score'])
            print(movie['channel'], curr_score, movie['title']) 

if args.subscribers:
    logger.info('list users')
    for subscriber in subscribers:
        print(subscriber['firstname'], subscriber['email'], subscriber['rating']) 

if args.get_movie:
    logger.info(f'search for movie "{args.get_movie}"')
    search_movies = available_movies.search(Query_obj.title.matches(args.get_movie))
    if search_movies:
        for movie in search_movies:
            print(json.dumps(movie, indent=2))
    else:
        print('No movies found')

if args.admin:
    logger.info(f'setting admin to "{args.admin}"')

    new_admin = subscribers.get(Query_obj.email == args.admin)
    if new_admin:
        curr_admin = subscribers.get(Query_obj.admin == True)
        subscribers.update({'admin' : False}, Query_obj.admin == True)

        subscribers.update({'admin' : True}, Query_obj.email == args.admin)
        update_phrase = f"Replaced \"{curr_admin['email']}\" with \"{new_admin['email']}\" as admin."
    else:
        update_phrase = f"Couldn't find \"{args.admin}\" in subscribers. Make sure he/she is a subscriber."

    print(update_phrase)
    logger.info(update_phrase)
    
db.close()