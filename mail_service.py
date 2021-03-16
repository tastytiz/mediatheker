import packages
import pandas as pd
import re
import logging 
from tinydb import TinyDB, Query
import subprocess
import yaml
from configparser import ConfigParser
import sys

# set script config
config_yaml = open('config.yaml','r')
config = yaml.load(config_yaml, Loader=yaml.FullLoader)
config_yaml.close()


db = TinyDB(config['DB']['path'])
available_movies = db.table(config['DB']['available_movies'])
subscribers = db.table(config['DB']['subscribers'])
run_info = db.table(config['DB']['run_info'])
Subs = Query()

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO, filename='mail_service.log')

mailer = packages.Mailer(config, subscribers, available_movies)
mails = mailer.get_mails()
movies = pd.DataFrame.from_dict(available_movies.all())
purpose = ''
stop_pat = r'[Ss]top'
rating_pat = r'\d\.*\,*\d*'
download_pat = r'[Dd]ownload'
subscribe_pat = r'[Ss]ubscribe'
all_pat = r'[Aa]ll'
sum_pat = r'[Ss]ummary'
rerun_pat = r'[Rr]erun'
feedback_pat = r'[Ff]eedback'
admin_mail = subscribers.get(Subs.admin == True)['email']
def_rating = float(config['MOVIES']['def_rating'])

if not admin_mail:
    logging.error('No Admin found! Make sure to have an admin set. Use "mediatheker.py -a admin@example.com" to register an admin.')
    sys.exit('No Admin found!')

for mail in mails:
    from_address = mail['from'][1]
    try:
        splitted_body = mail['body'].splitlines()
        # check if body is set, else ''
        if splitted_body:
            first_line = splitted_body[0]
        else:
            first_line = ''
        if subscribers.get(Subs.email == from_address):
            curr_subscriber = subscribers.get(Subs.email == from_address)
            admin_privileges = curr_subscriber['admin']
            #download
            # needs to be implemented
            if(re.findall(download_pat,first_line)):
                if admin_privileges:
                    movie_ids = splitted_body[1].split(',')

                    purpose = f'download {movie_ids}'
                    reply = mailer.prepare_reply(curr_subscriber,'download')
                    if reply:
                        mailer.send_mail(reply['to_address'], reply['subject'], reply['body'])
                else:
                    purpose = 'download, but no privileges'
            #rerun
            elif(re.findall(rerun_pat,first_line) or re.findall(rerun_pat, mail['subject'])):
                if admin_privileges:
                    latest_run = run_info.get(doc_id=len(run_info))
                    if latest_run['status'] != 'started':
                        subprocess.Popen(['python3', 'mediatheker.py', '-l'])
                        purpose = f'rerun mediatheker'
                        reply = mailer.prepare_reply(curr_subscriber,'rerun')
                    else:
                        purpose = f'rerun already ongoing'
                        reply = mailer.prepare_reply(curr_subscriber,'rerun-false')
                    if reply:
                        mailer.send_mail(reply['to_address'], reply['subject'], reply['body'])
                else:
                    purpose = 'rerun, but no privileges'
            #feedback
            elif(re.findall(feedback_pat,first_line) or re.findall(feedback_pat, mail['subject'])):
                mailer.send_mail(admin_mail,'FEEDBACK [{mail_from}] - {subject}'.format(mail_from=from_address, subject=mail['subject']), mail['body'])
                reply = mailer.prepare_reply(curr_subscriber,'feedback')
                if reply:
                    mailer.send_mail(reply['to_address'], reply['subject'], reply['body'])

                purpose = 'send feedback'
            #summary
            elif(re.findall(sum_pat,first_line) or re.findall(sum_pat, mail['subject'])):
                newsletter = mailer.prepare_newsletter(curr_subscriber, movies, 'summary')
                if newsletter:
                    mailer.send_mail(newsletter['to_address'], newsletter['subject'], newsletter['body'])

                purpose = 'send summary'
            #all
            elif(re.findall(all_pat,first_line) or re.findall(all_pat, mail['subject'])):
                newsletter = mailer.prepare_newsletter(curr_subscriber, movies, 'all')
                if newsletter:
                    mailer.send_mail(newsletter['to_address'], newsletter['subject'], newsletter['body'])

                purpose = 'send all'
            #stop
            elif(re.findall(stop_pat, first_line) or re.findall(stop_pat, mail['subject'])):
                subscribers.remove(Subs.email == curr_subscriber['email'])
                reply = mailer.prepare_reply(curr_subscriber,'stop')
                if reply:
                    mailer.send_mail(reply['to_address'], reply['subject'], reply['body'])
                
                purpose = 'stop'
            #rating
            elif(re.findall(rating_pat,first_line) or re.findall(rating_pat, mail['subject'])):
                res = re.findall(rating_pat,first_line) or re.findall(rating_pat, mail['subject'])
                rating = float(res[0].replace(',','.'))
                if rating > 10.0:
                    rating = 10.0
                elif rating < 0.0:
                    rating = 0.0
                subscribers.update({'rating' : rating}, Subs.email == curr_subscriber['email'])
                curr_subscriber = subscribers.get(Subs.email == from_address) # get updated subscriber
                reply = mailer.prepare_reply(curr_subscriber,'rating')
                if reply:
                    mailer.send_mail(reply['to_address'], reply['subject'], reply['body'])

                purpose = 'rating {res}'.format(res=rating) 
            #unknown
            else:
                mailer.send_mail(admin_mail,f'User [{from_address}] - {mail["subject"]}', mail['body'])
                reply = mailer.prepare_reply(curr_subscriber,'unknown')
                if reply:
                    mailer.send_mail(reply['to_address'], reply['subject'], reply['body'])
                purpose = 'unkown - user request'
        
        else:
            #subscribe
            if(re.findall(subscribe_pat, first_line) or re.findall(subscribe_pat, mail['subject'])):
                name_pat = r'([a-zöäüA-ZÖÄÜ]{2,})\s\w+'
                if re.findall(name_pat,mail['from'][0]):
                    subscriber_name = re.findall(name_pat,mail['from'][0])[0]
                else:
                    subscriber_name = '?'

                new_subscriber = {'firstname' : subscriber_name, 'email': from_address, 'admin' : False, 'first' : True, 'rating' : def_rating}
                subscribers.insert(new_subscriber)
                reply = mailer.prepare_reply(new_subscriber,'subscribe')
                mailer.send_mail(reply['to_address'], reply['subject'], reply['body'])

                mailer.send_newsletter(new_subscriber)
                
                purpose = f'subscribe {subscriber_name}, {from_address}'
            #unknown
            else:
                mailer.send_mail(admin_mail,'Foreign [{mail_from}] - {subject}'.format(mail_from=from_address, subject=mail['subject']), mail['body'])

                purpose = 'unkown - foreign request'

        logging.info(f"Served {from_address} with: {purpose}")
        mailer.delete_all_mails()
    except:
        logging.exception(f'Error while serving mail services for {from_address}:')

db.close()