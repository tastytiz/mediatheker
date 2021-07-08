import requests
import json
import pandas as pd
from bs4 import BeautifulSoup
from imdb import IMDb
import logging
import re
from tinydb import TinyDB, Query
import time
from datetime import datetime, timedelta

mt_logger = logging.getLogger('mediatheker.mt')

class Movieretriever:
    def __init__(self, config, latest_movies, available_movies, first_seen):
        self.config = config
        self.latest_movies = latest_movies
        self.available_movies = available_movies
        self.first_seen = first_seen
        self.Movies = Query()

    def create_unique(self, title, channel, runtime):
        match = re.findall(r'\(?([0-9A-Za-z]+)\)?', title)
        return "".join(match).lower() + channel + str(runtime)

    def init_movie_element(self):
        return {'unique' : '', 'title' : '', 'url' : '', 'download_url' : '', 'cover_url' : '', 'runtime' : '', 'plot' : '', 'year' : '', 'countries' : '', 'genres' : '', 'rating' : 0.0, 'imdbID' : '', 'channel' : '', 'language' : '', 'score': 0}

    def checkset_first_seen(self,movie):
        if not self.first_seen.get(self.Movies.unique == movie['unique']):
            self.first_seen.insert({'unique' : movie['unique'], 'first_seen' :  str(datetime.now().date())})
   
    def retrieve_movies(self,channels = ['ard', 'zdf', 'arte'], retries = 3):
        error = False
        if retries > 0:
            retries -= 1
            if 'ard' in channels:
                try:
                    self.get_ard_movies()
                    channels.remove('ard')
                    mt_logger.info("{counter} movies found for ARD".format(counter=self.latest_movies.count(self.Movies.channel == 'ard')))
                except:
                    error = True
                    mt_logger.exception("Error while retrieving ard movies:")
                    # raise

            if 'zdf' in channels:
                try:
                    self.get_zdf_movies()
                    channels.remove('zdf')
                    mt_logger.info("{counter} movies found for ZDF".format(counter=self.latest_movies.count(self.Movies.channel == 'zdf')))
                except:
                    error = True
                    mt_logger.exception("Error while retrieving zdf movies:")
                    # raise
            
            if 'arte' in channels:
                try:
                    self.get_arte_movies()
                    channels.remove('arte')
                    mt_logger.info("{counter} movies found for ARTE".format(counter=self.latest_movies.count(self.Movies.channel == 'arte')))
                except:
                    error = True
                    mt_logger.exception("Error while retrieving arte movies:")
                    # raise
            
            if error:
                mt_logger.info(f"Restarting movie retrival for {channels}. {retries} retries left.")
                return self.retrieve_movies(channels,retries)
            else:
                return True
        else:
            return False

    def get_zdf_movies(self):
        filme_url = self.config['ZDF']['filme_url']

        # get initial site
        response = requests.get(filme_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        articles = soup.find_all('article')
        links = []
        #search for Filmtipps section -> that one includes our movies
        for article in articles:
            article_title = article.find("h2", class_="cluster-title")
            if article_title and "Film-Highlights" in article_title:
                #get all items that are initially loaded by the website first
                links = re.findall(r'[\"\']actionDetail[\"\']:\s[\"\']Cluster:Film-Highlights.*Linkziel:(.*)[\"\']',article.prettify())
                #then get all teaser objects and read the info using another get request
                teasers = re.findall("data-teaser-xhr-url=\"(.*)\"",article.prettify())
                for teaser in teasers:
                    teaser_content = requests.get(teaser)
                    soup_teaser = BeautifulSoup(teaser_content.content, 'html.parser')
                    linkziel = re.findall("Linkziel:(.*)\"", soup_teaser.prettify())[0]
                    if re.compile(r'\d').search(linkziel): # only allow those links with a digit in the link list. Otherwise linkziel doesn't contain a movie
                        links.append(linkziel)

        for link in links:
            movie = self.init_movie_element()
            movie = self.zdf_helper(movie,link)
            movie['unique'] = self.create_unique(movie['title'], movie['channel'], movie['runtime'])
            self.latest_movies.upsert(movie, self.Movies.unique == movie['unique']) 
            self.checkset_first_seen(movie)

        # return movies #db

    def zdf_helper(self,movie,link):
        filme_url = self.config['ZDF']['filme_url']
        api_url = self.config['ZDF']['api_url']
        playerid = self.config['ZDF']['playerid']
        plot_length = int(self.config['MOVIES']['plot_length'])
        mime_types = self.config['MOVIES']['mime_types']

        movie['channel'] = 'zdf'
        link = link if ".html" in link else link + ".html"
        movie['url'] = link if "http" in link else filme_url + link
        curr_movie_page = requests.get(movie['url'])
        soup_movie = BeautifulSoup(curr_movie_page.content, 'html.parser')
        soup_movie_pretty = soup_movie.prettify()

        api_token = re.findall(r'\"apiToken\":\s\"([\w\d]*)\"',soup_movie_pretty)[0]
        content_url = re.findall(r'\"content\":\s\"(.*)\"',soup_movie_pretty)[0]

        api_response = requests.get(content_url,headers={'Api-Auth': 'Bearer {token}'.format(token=api_token)})

        api_json = json.loads(api_response.content)

        movie['title'] = api_json['title']
        movie['plot'] = api_json['leadParagraph'][:plot_length]
        main_video_content = api_json['mainVideoContent']['http://zdf.de/rels/target']
        movie['runtime'] = round(main_video_content['duration'] / 60)

        try:
            # temp fix. There seems to be sth wrong with:
            # {'title': 'Sieben Stunden', 'duration': 5255, 'visible': True, 'visibleFrom': '2021-06-04T05:00:00.000+02:00', 'visibleTo': '2021-06-11T05:00:00.000+02:00', 'aspectRatio': '16:9', 'profile': 'http://zdf.de/rels/content/content-video-vod-partner-player', 'self': '/content/documents/zdf/arte/arte-plus-7/vod-artede-sieben-stunden-100.json?profile=player', 'canonical': '/content/documents/vod-artede-sieben-stunden-100.json', 'streams': {'default': {'label': 'Normal', 'extId': 'video_artede_078114-000-A', 'http://zdf.de/rels/streams/ptmd-template': '/content/documents/vod-artede-sieben-stunden-100.json?profile=tmd'}}}
            download_json_url = api_url + main_video_content["http://zdf.de/rels/streams/ptmd-template"].replace('{playerId}',playerid)
            download_json_response = requests.get(download_json_url,headers={'Api-Auth': 'Bearer {token}'.format(token=api_token)})

            download_json = json.loads(download_json_response.content)
            formitaet_init = True
            for formitaet in download_json['priorityList']:
                formitaet_content = formitaet['formitaeten'][0]
                if formitaet_content['mimeType'] and formitaet_content['mimeType'] in mime_types:
                    for quality in formitaet_content['qualities']:
                        if formitaet_init:
                            movie['download_url'] = quality['audio']['tracks'][0]['uri']
                            formitaet_init = False
                        if quality['hd']:
                            movie['download_url'] = quality['audio']['tracks'][0]['uri']
        except:
            movie['download_url'] = movie['url']

        return movie

    def get_arte_movies(self):
        filme_url = self.config['ARTE']['filme_url']
        nextPage = True
        page=1
        movie_objects = []
        while(nextPage):
            page_url = filme_url + '?page={page}'.format(page=page)
            response = requests.get(page_url)
            soup = BeautifulSoup(response.content, 'html.parser')

            page_content = re.findall(r'window\.__INITIAL_STATE__\s=\s(.*);', soup.prettify())[0]
            page_json = json.loads(page_content)

            page_movies = page_json['pages']['list']['filme_de_\"{page}\"'.format(page=page)]['zones'][1]['data']
            movie_objects = movie_objects + page_movies

            if page_json['pages']['list']['filme_de_\"{page}\"'.format(page=page)]['zones'][1]['nextPage']:
                page += 1
            else:
                nextPage = False    

        for movie_object in movie_objects:
            movie = self.init_movie_element()
            movie = self.arte_helper(movie, movie_object)
            movie['unique'] = self.create_unique(movie['title'], movie['channel'], movie['runtime'])
            self.latest_movies.upsert(movie, self.Movies.unique == movie['unique']) 
            self.checkset_first_seen(movie)


    def arte_helper(self,movie, movie_object):
        api_token_url = self.config['ARTE']['token_url']
        language = self.config['ARTE']['lang']
        api_url = self.config['ARTE']['api_url'] + "{lang}/".format(lang=language)
        plot_length = int(self.config['MOVIES']['plot_length'])
        mime_types = self.config['MOVIES']['mime_types']

        response = requests.get(api_token_url)
        api_token = json.loads(response.content)['apiplayer']['token']

        movie['channel'] = 'arte'
        movie['url'] = movie_object['url']
        movie['title'] = movie_object['title']
        movie['plot'] = movie_object['shortDescription'][:plot_length]
        movie['runtime'] = round(movie_object['duration'] / 60)

        # in case vid_json cannot be set due to bad api request. Retry after certain amount of seconds
        attempts = 2
        sleep_time = 60
        for x in range(attempts):
            try:
                vid_response = requests.get(api_url + movie_object['programId'], headers= {'Authorization' : 'Bearer {token}'.format(token=api_token)})
                vid_json = json.loads(vid_response.content) 
            except:
                mt_logger.error(f"Couldn't retrieve download info for '{movie['title']}'. Attempt {x+1}/{attempts}")
                if x < (attempts - 1):
                    time.sleep(sleep_time)
                else:
                    raise
        
        streams = vid_json['videoJsonPlayer']['VSR']
        vid_lang_prio1 = r'^Deutsch$'
        vid_lang_prio2 = r'deutsch'
        vid_lang_prio3 = r'Originalfassung'
        vid_lang_prios = [vid_lang_prio1,vid_lang_prio2,vid_lang_prio3]
        lang_match = False
        curr_max_rate = 0
        curr_max_name = ''
        lang_short = ''

        for prioNumber, vid_lang in enumerate(vid_lang_prios):
            for vid in streams:
                curr_stream = streams[vid]
                if curr_stream['mimeType'] in mime_types:
                    if re.search(vid_lang, curr_stream['versionLibelle']): 
                        if curr_stream['bitrate'] > curr_max_rate:
                            curr_max_rate = curr_stream['bitrate']
                            curr_max_name = vid
                            lang_match=True
                            if prioNumber == 1:
                                lang_short = 'UT'
                            elif prioNumber == 2:
                                lang_short = 'OmU'
            if lang_match:
                break
        
        movie['language'] = lang_short
        movie['download_url'] = streams[curr_max_name]['url'] if lang_match else ''
        return movie


    def get_ard_movies(self):
        base_url = self.config['ARD']['mediathek_url']
        filme_url = self.config['ARD']['filme_url']
        section_names = self.config['ARD']['section_names']
        
        # get initial site
        response = requests.get(base_url + filme_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        sections = soup.find_all('section')
        
        #search for Filmtipps or besondere Filme section -> that one includes our movies. Break after found one
        found_best = False
        for section in sections:
            if not found_best:
                for section_name in section_names:
                    if section_name in section.prettify():
                        links = section.find_all('a')
                        found_best = True
                        break
            else:
                break

        #TODO: error handling einfügen falls keine Section mit Filmtipps gefunden
        #iterate through all movies found in the given section
        for link in links:
            movie = self.init_movie_element()
            movie = self.ard_helper(movie,link['href'])
            movie['unique'] = self.create_unique(movie['title'], movie['channel'], movie['runtime'])
            self.latest_movies.upsert(movie, self.Movies.unique == movie['unique']) 
            self.checkset_first_seen(movie)


        # return movies #db

    def ard_helper(self,movie, link):
        base_url = self.config['ARD']['mediathek_url']
        movie['channel'] = 'ard'
        plot_length = int(self.config['MOVIES']['plot_length'])
        api_url = self.config['ARD']['api_url']

        if 'http' in link:
            movie['url'] = link
        else:
            movie['url'] = base_url + link

        curr_movie = requests.get(movie['url'])
        soup_movie = BeautifulSoup(curr_movie.content, 'html.parser')

        scripts = soup_movie.find_all('script')

        var = scripts[len(scripts)-1] # get last script element as that one includes what we are looking for

        var_content = re.findall(self.config['ARD']['regex_wfc'], str(var))[0] if len(re.findall(self.config['ARD']['regex_wfc'], str(var))) > 0 else re.findall(self.config['ARD']['regex_fcv'], str(var))[0] # Fetched_context is the variable we need to read

        js = json.loads(var_content) #load as json
        movie_base = js[list(js.keys())[0]] # first key is the relevant one
        movie['title'] = movie_base['title']

        widgets = movie_base['widgets'][0]
        movie['plot'] = " ".join(widgets['synopsis'][:plot_length].split())

        # mediaCollection might be empty if this movie is under age restriction and its not night time
        # if widgets['mediaCollection']:
        #     print(movie['title'])
        #     print(widgets['mediaCollection'])
        #     movie['runtime'] = round(int(widgets['mediaCollection']['embedded']['_duration']) / 60) # convert from seconds to minutes
        #     #movie_download url needs to be converted to a dataframe first
        #     movie_download_array = widgets['mediaCollection']['embedded']['_mediaArray'][0]['_mediaStreamArray']
        # else:
        contentId = re.findall(r'[\"\']contentId[\"\']:\s*(\d+)', var_content)[0]
        api_response = requests.get(api_url + contentId)
        api_json = json.loads(api_response.content)
        if(api_json['_duration']):
            movie['runtime'] = round(int(api_json['_duration']) / 60) # convert from seconds to minutes
        #movie_download url needs to be converted to a dataframe first
        if api_json['_mediaArray']:
            movie_download_array = api_json['_mediaArray'][0]['_mediaStreamArray']

        movie_download_df = pd.DataFrame(data=movie_download_array)

        #then remove auto as quality option
        movie_download_df.drop(movie_download_df[movie_download_df['_quality'] == 'auto'].index, axis=0,inplace=True)
        movie_download_df = movie_download_df.astype({'_quality' : int})
        #finally find element with highest quality number
        curr_max = movie_download_df.iloc[0]
        for _, elem in movie_download_df.iterrows():
            if elem['_quality'] > curr_max['_quality']:
                curr_max = elem.copy()

        if isinstance(curr_max['_stream'],list):
            stream = curr_max['_stream'][0]
        else:
            stream = curr_max['_stream']

        if 'http' in stream:
            movie['download_url'] = stream
        else:
            movie['download_url'] = "https:" + stream

        return movie

    # def add_info_support(self,movie_result,movie):
    #     if 'kind' in movie_result:
    #         if 'movie' in movie_result['kind']:
    #             return True
    #         #ard specific:
    #         elif 'tv series' in movie_result['kind'] and movie['channel'] == 'ard':
    #             if 'original title' in movie_result:
    #                 if 'Tatort' in movie_result['original title']:
    #                     return True
    #             elif 'episode of' in movie_result:
    #                 if 'Tatort' in movie_result['episode of']:
    #                     return True
    #     return False

    def imdb_matchmaking(self,imdb_movies, movie):
        ia = IMDb()
        imdb_movies_count = len(imdb_movies)
        max_loops = self.config['IMDB']['movie_checks'] if imdb_movies_count >= self.config['IMDB']['movie_checks'] else imdb_movies_count
        winner_threshold = self.config['IMDB']['winner_threshold']
        looser_threshold = self.config['IMDB']['looser_threshold']
        runtime_max = self.config['IMDB']['runtime_max']
        title_max = self.config['IMDB']['title_max']
        episode_max = self.config['IMDB']['episode_max']
        is_movie = self.config['IMDB']['movie']

        if imdb_movies_count == 0:
            return 0, False

        choices = []
        for j in range(0,max_loops):
            matchpoints = 0
            movie_result = ia.get_movie(imdb_movies[j].movieID)
            if imdb_movies_count == 1:
                return 100, movie_result

            # title matching
            if 'title' in movie_result:
                movie_title = "".join(re.findall('([a-zA-Z]*)', movie['title'])).lower()
                result_title = "".join(re.findall('([a-zA-Z]*)', movie_result['title'])).lower()
                zipped = zip(movie_title,result_title)
                tup_points = 0
                for tup in zipped:
                    if tup[0] == tup[1]:
                        tup_points +=1
                matchpoints += int((tup_points/(len(movie_title)) * title_max))

            # runtime matching
            if 'runtimes' in movie_result:
                matchpoints += 1
                runtime_match = abs(int(movie_result['runtimes'][0]) - movie['runtime']) - runtime_max
                if runtime_match < 0:
                    matchpoints += (runtime_match * -1)

            # kind matching. Mostly for ARD series Tatort and Polizeiruf 110
            if 'kind' in movie_result:
                # matchpoints +=1
                if 'movie' in movie_result['kind']:
                    matchpoints += is_movie
                #ard specific:
                elif ('episode' in movie_result['kind'] or 'tv series' in movie_result['kind']) and movie['channel'] == 'ard':
                    if 'episode of' in movie_result:
                        if 'title' in movie_result['episode of']:
                            if 'Tatort' in movie_result['episode of']['title']:
                                matchpoints += episode_max
                            elif 'Polizeiruf 110' in movie_result['episode of']['title']:
                                matchpoints += episode_max
                    elif 'original title' in movie_result:
                        if 'Tatort' in movie_result['original title']:
                            matchpoints += episode_max
                        elif 'Polizeiruf 110' in movie_result['original title']:
                            matchpoints += episode_max
            
            # direct winner if certain threshold met
            if matchpoints >= winner_threshold:
                return matchpoints, movie_result
            else:
                choices.append({'matchpoints' : matchpoints, 'content' : movie_result})

        # otherwise choose the result with the highest score
        curr_best_choice = choices[0]
        for choice in choices:
            if choice['matchpoints'] > curr_best_choice['matchpoints']:
                curr_best_choice = choice
        
        # only return movie if minimum score was reached
        if curr_best_choice['matchpoints'] > looser_threshold:
            return curr_best_choice['matchpoints'],curr_best_choice['content']
        else:
            return  0, False


    def add_info(self,movie):
        # create an instance of the IMDb class
        ia = IMDb()
        
        imdb_movies = ia.search_movie(movie['title'])
        score, movie_result = self.imdb_matchmaking(imdb_movies,movie)
        movie['score'] = score
        # search_movies_count = len(search_movies)
        # found_movie = False
        # r_threshold = 10 # movie runtime can vary by r_threshold minutes in order to make it a likely match #alternative
        # movie_result = ''
        # j = 0
        
        # # get first movie from iMDb. There are some special cases for certain channels
        # while not found_movie:
        #     if(j < search_movies_count):
        #         movie_result = ia.get_movie(search_movies[j].movieID)
        #     else:
        #         break
        #     if 'runtimes' in movie_result:
        #         if (int(movie_result['runtimes'][0]) - r_threshold) <= movie['runtime'] and (int(movie_result['runtimes'][0]) + r_threshold) >= movie['runtime']:
        #         # if int(movie_result['runtimes'][0]) == movie['runtime']: # same runtime = match --> unlikely
        #             found_movie = self.add_info_support(movie_result,movie)
        #     else:
        #         found_movie = self.add_info_support(movie_result,movie)
        #     j += 1

        # # add found info to the movie object 
        if movie_result:
            if 'genres' in movie_result:
                movie['genres'] = ', '.join(movie_result['genres'])
            
            if 'rating' in movie_result:
                movie['rating'] = movie_result['rating']
            
            if 'countries' in movie_result:
                movie['countries'] = ', '.join(movie_result['countries'])
            
            if 'cover url' in movie_result:
                movie['cover_url'] = movie_result['cover url']
            
            if 'imdbID' in movie_result:
                movie['imdbID'] = movie_result['imdbID']
            
            if 'year' in movie_result:
                movie['year'] = movie_result['year']
        else:
            movie['rating'] = 0.0
        return movie

    def update_movie_list(self):
        new_list = pd.DataFrame.from_dict(self.latest_movies.all())[['title','url','download_url','plot','runtime','channel', 'unique', 'language']]
        old_list = pd.DataFrame.from_dict(self.available_movies.all())[['unique','cover_url','year','countries','genres','rating','imdbID', 'score', 'type']]

        old_list['type'] = 'old'
        new_list = new_list.merge(old_list, how='left', on='unique')
        new_list['rating'].fillna(0.0, inplace=True) # correct possible movie issue when there was no rating passed
        # new_list.loc[new_list['type'] == 'new', 'type'] = 'old' # previously new movies are considered old now
        new_list['type'].fillna('new', inplace=True)
        new_list.drop_duplicates(['unique'], ignore_index=True,inplace=True)
        new_list['movie_id'] = new_list.index # save newly ordered index

        self.available_movies.truncate()
        self.available_movies.insert_multiple(new_list.to_dict('records'))
        av_count=len(self.available_movies)
        av_name = self.config['DB']['available_movies']
        mt_logger.info(f'{av_count} movies saved to {av_name} table.')

        imdb_counter = 0
        today = datetime.now().date()
        allegedly_new = self.available_movies.search(self.Movies.type == 'new')
        allegedly_new_count = len(allegedly_new)
        for movie in allegedly_new:
            curr_movie_query = self.Movies.unique == movie['unique']
            movie = self.add_info(movie)
            self.available_movies.update(movie, curr_movie_query)
            # sometimes a movie already existed already, but wasn't retrieved for some reason today
            # in this case change the type from new to old
            movie_first_seen = self.first_seen.get(curr_movie_query)
            if today != datetime.strptime(movie_first_seen['first_seen'],'%Y-%m-%d').date():
                self.available_movies.update({'type' : 'old'}, curr_movie_query)
            if isinstance(movie['imdbID'],str):
                imdb_counter +=1
        mt_logger.info(f"iMDb info found and added to {imdb_counter}/{allegedly_new_count} new movies")

        #logging results
        new_count = len(self.available_movies.search(self.Movies.type == 'new'))
        old_count = len(self.available_movies.search(self.Movies.type == 'old'))
        allegedly_updated_count = allegedly_new_count - new_count
        removed = len(old_list) - (old_count - allegedly_updated_count)
        
        mt_logger.info(f'Movie List Update result: {new_count} new; {old_count} old; {allegedly_updated_count} allegedly new (contained in old); {removed} removed')

        # remove movies from first_seen db if they pass the set days of storage
        fs_name = self.config['DB']['first_seen']
        before_count = len(self.first_seen)

        storage_days = self.config['DB']['first_seen_storage']
        removal_date = today - timedelta(days= storage_days)
        self.first_seen.remove(self.Movies.first_seen == str(removal_date))

        after_count = len(self.first_seen)
        mt_logger.info(f'{before_count-after_count} movies removed from {fs_name} on schedule as they first appeared {storage_days} days ago.')




